import hashlib
import os
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import unquote

import questionary
from requests.exceptions import RequestException
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from src import config
from src.display import console
from src.utils import extract_archive, get_http_session

PARTIAL_SUFFIX = ".partial"
MAX_DOWNLOAD_ATTEMPTS = 5


def _verify_checksum(local_path, game):
    """Confere o hash do arquivo baixado contra o valor oficial do archive.org."""
    expected = game.get("md5") or game.get("sha1")
    if not expected:
        return None
    # md5/sha1 aqui são só checksum de integridade contra o archive.org, não uso criptográfico.
    algo = (
        hashlib.md5(usedforsecurity=False)
        if game.get("md5")
        else hashlib.sha1(usedforsecurity=False)
    )
    with open(local_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 256), b""):
            algo.update(chunk)
    actual = algo.hexdigest()
    return actual.lower() == expected.lower()


def _download_with_resume(url, local_path, expected_size, progress, task_id):
    """Baixa com retomada via Range: se a conexão cair no meio (comum com
    servidores do archive.org sob carga), a próxima tentativa continua de
    onde parou em vez de reiniciar do zero. Progresso é reportado numa task
    de um Progress compartilhado, pra download_games poder rodar vários ao
    mesmo tempo com todas as barras visíveis juntas."""
    session = get_http_session()

    for attempt in range(1, MAX_DOWNLOAD_ATTEMPTS + 1):
        resume_from = os.path.getsize(local_path) if os.path.exists(local_path) else 0
        if expected_size and resume_from >= expected_size:
            return

        headers = {"Range": f"bytes={resume_from}-"} if resume_from else {}
        try:
            with session.get(
                url, stream=True, timeout=(10, 60), headers=headers
            ) as response:
                if response.status_code == 416:
                    return  # já temos o arquivo completo
                response.raise_for_status()

                resumed = response.status_code == 206
                if not resumed:
                    resume_from = 0  # servidor ignorou o Range, manda o arquivo inteiro

                content_length = int(response.headers.get("Content-Length", 0))
                total = expected_size or (content_length + resume_from) or None
                progress.update(task_id, total=total, completed=resume_from)

                with open(local_path, "ab" if resumed else "wb") as f:
                    for chunk in response.iter_content(chunk_size=1024 * 64):
                        f.write(chunk)
                        progress.update(task_id, advance=len(chunk))
            return
        except RequestException as e:
            if attempt == MAX_DOWNLOAD_ATTEMPTS:
                raise
            progress.console.print(
                f"[yellow]Conexão caiu (tentativa {attempt}/{MAX_DOWNLOAD_ATTEMPTS}): {e}"
                f" — retomando de {resume_from / (1024*1024):.1f} MB...[/yellow]"
            )


def download_game(game, progress, task_id, dest_root=None):
    dest_root = dest_root or config.ROMS_ROOT
    url = game["link"]
    filename = unquote(os.path.basename(url))
    dest_dir = os.path.join(
        dest_root, game.get("folder") or game.get("console", "default")
    )
    os.makedirs(dest_dir, exist_ok=True)
    final_path = os.path.join(dest_dir, filename)
    partial_path = final_path + PARTIAL_SUFFIX

    # Depois de extrair .zip/.7z/.rar o arquivo original não existe mais (virou
    # .zso/.iso/pasta com outra extensão) — checar só final_path faria baixar
    # e extrair tudo de novo a cada execução. Mesmo nome-base (sem extensão)
    # já presente na pasta é sinal de que o jogo já foi baixado.
    base_name = os.path.splitext(filename)[0]
    already_present = os.path.exists(final_path) or any(
        os.path.splitext(f)[0] == base_name
        for f in os.listdir(dest_dir)
        if not f.endswith(PARTIAL_SUFFIX)
    )
    if already_present:
        progress.console.print(f"[yellow]Já baixado, pulando:[/yellow] {filename}")
        progress.update(task_id, completed=1, total=1)
        return final_path

    try:
        _download_with_resume(
            url, partial_path, game.get("size_bytes"), progress, task_id
        )
    except KeyboardInterrupt:
        mb = (
            os.path.getsize(partial_path) / (1024 * 1024)
            if os.path.exists(partial_path)
            else 0
        )
        progress.console.print(
            f"\n[yellow]{game['name'][:40]}: cancelado — {mb:.1f} MB salvos (parcial). "
            f"Baixe de novo depois pra continuar de onde parou, ou rode /clean pra descartar.[/yellow]"
        )
        raise

    os.rename(partial_path, final_path)

    ok = _verify_checksum(final_path, game)
    if ok is True:
        progress.console.print(f"[green]Hash verificado — {filename} íntegro.[/green]")
    elif ok is False:
        progress.console.print(
            f"[bold red]ATENÇÃO: hash de {filename} não confere com o archive.org! "
            "Arquivo pode estar corrompido ou adulterado.[/bold red]"
        )

    ext = os.path.splitext(final_path)[1].lower()
    if ext in (".zip", ".7z", ".rar"):
        progress.console.print(f"[dim]Extraindo {filename}...[/]")
        if extract_archive(final_path, dest_dir):
            progress.console.print(
                f"[green]{filename}: extraído — pronto pra jogar.[/green]"
            )
        else:
            progress.console.print(
                f"[bold red]Falha ao extrair {filename}. Arquivo compactado mantido em:"
                f"[/bold red] {final_path}"
            )

    _download_covers(game, progress)

    return final_path


def _download_covers(game, progress):
    """Busca a capa (RAWG) e salva no formato de PCSX2/RetroArch, se achar."""
    from src.metadata_manager import download_covers_for_emulators
    from src.scraping import fetch_game_details

    console_name = game.get("console", "")
    details = fetch_game_details(game["name"], console_name)
    if not details or not details.get("cover_url"):
        return

    saved = download_covers_for_emulators(
        details["cover_url"], game["name"], console_name
    )
    where = [k for k, v in saved.items() if v]
    if where:
        progress.console.print(
            f"[green]{game['name'][:40]}: capa salva ({', '.join(where)}).[/green]"
        )


def download_games(games):
    """Baixa vários jogos em paralelo (config.MAX_CONCURRENT_DOWNLOADS de cada
    vez), com uma barra de progresso por jogo, todas visíveis ao mesmo tempo."""
    with Progress(
        "[progress.description]{task.description}",
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task_ids = {
            id(game): progress.add_task(game["name"][:40], total=None, start=False)
            for game in games
        }

        def _run(game):
            task_id = task_ids[id(game)]
            progress.start_task(task_id)
            return game, download_game(game, progress, task_id)

        executor = ThreadPoolExecutor(
            max_workers=max(1, config.MAX_CONCURRENT_DOWNLOADS)
        )
        futures = [executor.submit(_run, game) for game in games]
        try:
            for future in as_completed(futures):
                try:
                    game, path = future.result()
                    progress.console.print(f"[green]✓[/green] {path}")
                except Exception as e:
                    progress.console.print(f"[red]✗[/red] {e}")
            executor.shutdown(wait=True)
        except KeyboardInterrupt:
            # Não dá pra matar uma thread no meio da leitura de um chunk —
            # cancela o que ainda não começou e deixa o que já está baixando
            # terminar sozinho (fica íntegro, ou vira .partial retomável).
            progress.console.print(
                "[yellow]Cancelando fila — downloads já em andamento vão "
                "terminar sozinhos.[/yellow]"
            )
            executor.shutdown(wait=True, cancel_futures=True)


def clean_partial_downloads():
    """Lista e remove arquivos .partial deixados por downloads cancelados/falhos."""
    found = []
    for root, _dirs, files in os.walk(config.ROMS_ROOT):
        for f in files:
            if f.endswith(PARTIAL_SUFFIX):
                path = os.path.join(root, f)
                found.append((path, os.path.getsize(path)))

    if not found:
        console.print(
            "[green]Nada pra limpar — nenhum download incompleto encontrado.[/green]"
        )
        return

    total_mb = sum(sz for _, sz in found) / (1024 * 1024)
    console.print(
        f"[yellow]{len(found)} download(s) incompleto(s), {total_mb:.1f} MB no total:[/yellow]"
    )
    for path, sz in found:
        name = os.path.basename(path)[: -len(PARTIAL_SUFFIX)]
        console.print(f"  {name}  ({sz / (1024*1024):.1f} MB)")

    if questionary.confirm("Apagar todos?", default=True).ask():
        for path, _ in found:
            os.remove(path)
        console.print("[green]Limpo.[/green]")


def delete_game(game):
    """Apaga o(s) arquivo(s) locais do jogo (rom + pasta extraída, se houver)
    e as capas associadas. Casa pelo nome-base do arquivo, mesmo esquema do
    dedup de download. Retorna a lista do que foi apagado (vazia se nada
    encontrado localmente — o jogo pode nunca ter sido baixado)."""
    from src.metadata_manager import delete_covers

    dest_dir = os.path.join(
        config.ROMS_ROOT, game.get("folder") or game.get("console", "default")
    )
    if not os.path.isdir(dest_dir):
        return []

    filename = unquote(os.path.basename(game["link"]))
    base_name = os.path.splitext(filename)[0]

    deleted = []
    for f in os.listdir(dest_dir):
        if f.endswith(PARTIAL_SUFFIX) or os.path.splitext(f)[0] != base_name:
            continue
        path = os.path.join(dest_dir, f)
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
        deleted.append(f)

    delete_covers(game["name"], game.get("console", ""))

    return deleted
