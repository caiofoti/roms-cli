import hashlib
import os
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


def _download_with_resume(url, local_path, expected_size, task_label):
    """Baixa com retomada via Range: se a conexão cair no meio (comum com
    servidores do archive.org sob carga), a próxima tentativa continua de
    onde parou em vez de reiniciar do zero. Ctrl+C propaga pra quem chamou
    (download_game cuida de deixar o .partial no lugar e avisar)."""
    session = get_http_session()

    for attempt in range(1, MAX_DOWNLOAD_ATTEMPTS + 1):
        resume_from = os.path.getsize(local_path) if os.path.exists(local_path) else 0
        if expected_size and resume_from >= expected_size:
            return

        headers = {"Range": f"bytes={resume_from}-"} if resume_from else {}
        try:
            with session.get(url, stream=True, timeout=(10, 60), headers=headers) as response:
                if response.status_code == 416:
                    return  # já temos o arquivo completo
                response.raise_for_status()

                resumed = response.status_code == 206
                if not resumed:
                    resume_from = 0  # servidor ignorou o Range, manda o arquivo inteiro

                content_length = int(response.headers.get("Content-Length", 0))
                total = expected_size or (content_length + resume_from) or None

                with Progress(
                    "[progress.description]{task.description}",
                    BarColumn(),
                    DownloadColumn(),
                    TransferSpeedColumn(),
                    TimeRemainingColumn(),
                    console=console,
                ) as progress:
                    task = progress.add_task(task_label, total=total, completed=resume_from)
                    with open(local_path, "ab" if resumed else "wb") as f:
                        for chunk in response.iter_content(chunk_size=1024 * 64):
                            f.write(chunk)
                            progress.update(task, advance=len(chunk))
            return
        except RequestException as e:
            if attempt == MAX_DOWNLOAD_ATTEMPTS:
                raise
            console.print(
                f"[yellow]Conexão caiu (tentativa {attempt}/{MAX_DOWNLOAD_ATTEMPTS}): {e}"
                f" — retomando de {resume_from / (1024*1024):.1f} MB...[/yellow]"
            )


def download_game(game, dest_root=None):
    dest_root = dest_root or config.ROMS_ROOT
    url = game["link"]
    filename = unquote(os.path.basename(url))
    dest_dir = os.path.join(dest_root, game.get("folder") or game.get("console", "default"))
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
        console.print(f"[yellow]Já baixado, pulando:[/yellow] {filename}")
        return final_path

    try:
        _download_with_resume(url, partial_path, game.get("size_bytes"), game["name"][:40])
    except KeyboardInterrupt:
        mb = os.path.getsize(partial_path) / (1024 * 1024) if os.path.exists(partial_path) else 0
        console.print(
            f"\n[yellow]Download cancelado — {mb:.1f} MB salvos (parcial). "
            f"Baixe de novo depois pra continuar de onde parou, ou rode /clean pra descartar.[/yellow]"
        )
        raise

    os.rename(partial_path, final_path)

    ok = _verify_checksum(final_path, game)
    if ok is True:
        console.print("[green]Hash verificado — arquivo íntegro.[/green]")
    elif ok is False:
        console.print(
            "[bold red]ATENÇÃO: hash não confere com o archive.org! "
            "Arquivo pode estar corrompido ou adulterado.[/bold red]"
        )

    ext = os.path.splitext(final_path)[1].lower()
    if ext in (".zip", ".7z", ".rar"):
        console.print(f"[dim]Extraindo {filename}...[/]")
        if extract_archive(final_path, dest_dir):
            console.print("[green]Extraído — pronto pra jogar.[/green]")
        else:
            console.print(
                "[bold red]Falha ao extrair. Arquivo compactado mantido em:"
                f"[/bold red] {final_path}"
            )

    _download_covers(game)

    return final_path


def _download_covers(game):
    """Busca a capa (RAWG) e salva no formato de PCSX2/RetroArch, se achar."""
    from src.metadata_manager import download_covers_for_emulators
    from src.scraping import fetch_game_details

    console_name = game.get("console", "")
    details = fetch_game_details(game["name"], console_name)
    if not details or not details.get("cover_url"):
        console.print("[dim]Capa não encontrada (RAWG sem resultado).[/dim]")
        return

    saved = download_covers_for_emulators(details["cover_url"], game["name"], console_name)
    where = [k for k, v in saved.items() if v]
    if where:
        console.print(f"[green]Capa salva ({', '.join(where)}).[/green]")
    else:
        console.print("[dim]Capa encontrada mas não salva (emulador não configurado/instalado).[/dim]")


def download_games(games):
    for game in games:
        console.print(f"\n{game['name']}")
        try:
            path = download_game(game)
            console.print(f"[green]✓[/green] {path}")
        except KeyboardInterrupt:
            console.print("[yellow]Fila de downloads interrompida.[/yellow]")
            return
        except Exception as e:
            console.print(f"[red]✗[/red] {e}")


def clean_partial_downloads():
    """Lista e remove arquivos .partial deixados por downloads cancelados/falhos."""
    found = []
    for root, _dirs, files in os.walk(config.ROMS_ROOT):
        for f in files:
            if f.endswith(PARTIAL_SUFFIX):
                path = os.path.join(root, f)
                found.append((path, os.path.getsize(path)))

    if not found:
        console.print("[green]Nada pra limpar — nenhum download incompleto encontrado.[/green]")
        return

    total_mb = sum(sz for _, sz in found) / (1024 * 1024)
    console.print(f"[yellow]{len(found)} download(s) incompleto(s), {total_mb:.1f} MB no total:[/yellow]")
    for path, sz in found:
        name = os.path.basename(path)[: -len(PARTIAL_SUFFIX)]
        console.print(f"  {name}  ({sz / (1024*1024):.1f} MB)")

    if questionary.confirm("Apagar todos?", default=True).ask():
        for path, _ in found:
            os.remove(path)
        console.print("[green]Limpo.[/green]")
