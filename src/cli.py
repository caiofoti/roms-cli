import argparse
import hashlib
import logging
import os
from urllib.parse import unquote

import questionary
from requests.exceptions import RequestException
from rich.console import Console
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.table import Table
from thefuzz import fuzz

from src import config
from src.config import CONSOLES_ARCHIVE, set_roms_root
from src.scraping import get_games_for_console_cached
from src.utils import extract_archive, get_http_session

console = Console()

PAGE_SIZE = 10
PARTIAL_SUFFIX = ".partial"


def pick_console():
    return questionary.select(
        "Console:", choices=sorted(CONSOLES_ARCHIVE.keys())
    ).ask()


def resolve_console_name(partial):
    """Aceita nome exato ou aproximado do console (busca por similaridade)."""
    if partial in CONSOLES_ARCHIVE:
        return partial
    best = max(
        CONSOLES_ARCHIVE.keys(),
        key=lambda name: fuzz.partial_ratio(partial.lower(), name.lower()),
    )
    return best


def _match_score(query, name):
    """token_set_ratio testado contra WRatio numa base real de nomes de ROM: WRatio
    dava o mesmo score pra títulos totalmente diferentes (ex: "God of War" empatava
    com "Crash Bandicoot" numa busca por Crash). token_set_ratio discrimina melhor
    porque ignora ordem/repetição de palavras sem inflar por tamanho de string.
    Substring exata sempre vence (resultado óbvio primeiro)."""
    if query in name:
        return 100
    return fuzz.token_set_ratio(query, name)


def search_games(games, query, limit=None):
    """Retorna (resultados_limitados, total_de_matches), ordenados por
    relevância (score desc) e, em empate, por tamanho do nome (mais curto/direto primeiro)."""
    limit = limit or config.DEFAULT_RESULT_LIMIT
    if not query:
        ordered = sorted(games, key=lambda g: g["name"].lower())
        return ordered[:limit], len(ordered)

    query_l = query.lower()
    scored = [(g, _match_score(query_l, g["name"].lower())) for g in games]
    scored = [(g, s) for g, s in scored if s >= config.MIN_SIMILARITY]
    scored.sort(key=lambda pair: (-pair[1], len(pair[0]["name"])))
    return [g for g, _ in scored[:limit]], len(scored)


def _format_downloads(n):
    if n is None:
        return "-"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


def _archive_stats_cols(game):
    """Downloads e nota são do item/coleção do archive.org inteiro (não por ROM
    individual — o archive.org não expõe isso por arquivo), servem como sinal
    de quão usada/confiável é a fonte de onde o jogo vem."""
    downloads = _format_downloads(game.get("archive_downloads"))
    rating = game.get("archive_rating")
    rating_str = f"{rating:.1f}" if rating is not None else "-"
    return downloads, rating_str


def show_results(matches, total=None):
    """Tabela simples sem paginação — usada pelo modo direto (--console/--query)."""
    if total is not None and total > len(matches):
        console.print(
            f"[dim]Mostrando {len(matches)} de {total} resultados — "
            f"refine a busca pra ver melhor.[/dim]"
        )
    table = Table(show_header=True, header_style="bold")
    table.add_column("#", width=4)
    table.add_column("Jogo")
    table.add_column("Downloads", justify="right", width=9)
    table.add_column("★", justify="right", width=4)
    table.add_column("Tamanho", justify="right")
    for i, g in enumerate(matches, 1):
        table.add_row(str(i), g["name"], *_archive_stats_cols(g), g["size_str"])
    console.print(table)


def show_page(matches, page):
    """Página de resultados com numeração absoluta e estável — /download <n>
    continua se referindo ao mesmo jogo em qualquer página."""
    total_pages = max(1, (len(matches) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * PAGE_SIZE
    page_items = matches[start:start + PAGE_SIZE]

    table = Table(show_header=True, header_style="bold")
    table.add_column("#", width=4)
    table.add_column("Jogo")
    table.add_column("Downloads", justify="right", width=9)
    table.add_column("★", justify="right", width=4)
    table.add_column("Tamanho", justify="right")
    for i, g in enumerate(page_items, start=start + 1):
        table.add_row(str(i), g["name"], *_archive_stats_cols(g), g["size_str"])
    console.print(table)
    console.print(
        f"[dim]Página {page + 1}/{total_pages} · {len(matches)} resultado(s)  "
        f"·  /next /prev pra navegar  ·  /download <n>[,<n>...] pra baixar[/dim]"
    )
    return page


def pick_games(matches):
    """Seleção via checkbox — usada só no modo direto (--console/--query) fora do chat."""
    choices = [
        questionary.Choice(f"{g['name']}  [{g['size_str']}]", value=g)
        for g in matches
    ]
    return (
        questionary.checkbox(
            "Selecione (espaço) e confirme (enter):", choices=choices
        ).ask()
        or []
    )


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


MAX_DOWNLOAD_ATTEMPTS = 5


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

    if os.path.exists(final_path):
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


def run_direct(console_arg, query, limit, yes):
    console_name = resolve_console_name(console_arg)
    if console_name != console_arg:
        console.print(f"[dim]Console mais próximo de '{console_arg}': {console_name}[/dim]")

    with console.status(f"Carregando catálogo de {console_name}..."):
        games = get_games_for_console_cached(console_name)

    if not games:
        console.print("[red]Nenhum jogo encontrado para esse console.[/red]")
        return

    matches, total = search_games(games, query, limit=limit)
    if not matches:
        console.print("[yellow]Nenhum resultado.[/yellow]")
        return

    show_results(matches, total)

    if yes:
        download_games(matches)
        return

    selected = pick_games(matches)
    if selected:
        download_games(selected)


def _build_top_list(console_name, games_cache):
    """Cruza os melhores avaliados do RAWG com o catálogo baixável: retorna None
    se não há como buscar (sem chave/mapeamento), [] se nada bateu, ou a lista
    curada (cada item é o jogo do catálogo + rating_100 do RAWG)."""
    from src.scraping import fetch_top_rated_titles

    with console.status("Buscando melhores avaliados (RAWG)..."):
        top_titles = fetch_top_rated_titles(console_name)

    if not top_titles:
        return None

    if console_name not in games_cache:
        games_cache[console_name] = _load_games(console_name)
    games = games_cache[console_name]
    if not games:
        return []

    curated = []
    seen = set()
    for t in top_titles:
        matches, _ = search_games(games, t["name"], limit=1)
        if matches and matches[0]["name"] not in seen:
            game = dict(matches[0])
            game["rating_100"] = t["rating_100"]
            curated.append(game)
            seen.add(game["name"])

    curated.sort(key=lambda g: g["rating_100"], reverse=True)
    return curated


def _load_games(console_name):
    with console.status(f"Carregando catálogo de {console_name}..."):
        try:
            return get_games_for_console_cached(console_name)
        except Exception as e:
            logging.error(f"Erro ao carregar catálogo: {e}")
            return []


def show_game_info(game, console_name):
    """Busca nota, gêneros e descrição via RAWG (precisa de chave de API no .env)."""
    from src.scraping import fetch_game_details

    with console.status("Buscando informações..."):
        details = fetch_game_details(game["name"], console_name)

    if not details:
        console.print(
            "[yellow]Sem metadados disponíveis — configure RAWG_API_KEY no .env, "
            "ou o jogo não foi encontrado na base.[/yellow]"
        )
        return

    console.print(f"\n[bold]{details['api_title']}[/bold]  [dim]({details['api_source']})[/dim]")
    if details.get("rating_100") is not None:
        console.print(f"Nota: {details['rating_100']}/100")
    if details.get("release_date"):
        console.print(f"Lançamento: {details['release_date']}")
    if details.get("genres"):
        console.print(f"Gêneros: {', '.join(details['genres'])}")
    if details.get("description"):
        desc = details["description"]
        if len(desc) > 400:
            desc = desc[:400].rsplit(" ", 1)[0] + "..."
        console.print(f"\n{desc}")
    if details.get("cover_url"):
        console.print(f"\n[dim]Capa: {details['cover_url']}[/dim]")
    console.print()


CONSOLE_ALIASES = {folder.lower(): name for name, (folder, _ids) in CONSOLES_ARCHIVE.items()}

HELP_TEXT = """[bold]Comandos:[/bold]
  [cyan]/console [nome][/cyan]     escolhe/troca o console (sem nome abre um menu)
  [cyan]/back[/cyan]              desmarca o console atual, volta ao estado inicial
  [cyan]/clear[/cyan]             limpa a tela
  [cyan]/consoles[/cyan]          lista os aliases de console (gb, gba, ps2, psx...)
  [cyan]<texto>[/cyan]            busca no console atual (sem precisar de comando)
  [cyan]/next[/cyan] / [cyan]/prev[/cyan]      pagina os resultados da última busca
  [cyan]/download <n>[,<n>...][/cyan]  baixa o(s) resultado(s) pelo número mostrado
  [cyan]/info <n>[/cyan]          nota, gêneros e descrição do resultado (RAWG)
  [cyan]/top[/cyan]               melhores avaliados (RAWG) já cruzados com o catálogo
  [cyan]/clean[/cyan]             lista e apaga downloads incompletos (.partial)
  [cyan]/config[/cyan]            tela de configurações (pasta, limites)
  [cyan]/root <pasta>[/cyan]      atalho rápido pra mudar a pasta de ROMs
  [cyan]/help[/cyan]              mostra essa ajuda
  [cyan]/quit[/cyan]              sai

[dim]Durante um download: Ctrl+C cancela só ele (não fecha o programa) e guarda
o progresso pra continuar depois.[/dim]"""


def print_banner():
    console.print(f"\n[bold]Roms Downloader[/bold]  [dim]{len(CONSOLES_ARCHIVE)} consoles · {config.ROMS_ROOT}[/dim]")
    console.print("[dim]/console <sistema> pra começar · /help pra ver todos os comandos[/dim]")
    if not os.getenv("RAWG_API_KEY"):
        console.print(
            "[yellow]Aviso:[/yellow] RAWG_API_KEY não configurada — /info, /top e "
            "capas de jogo não vão funcionar até você copiar .env.example para .env "
            "e colocar sua chave (grátis em https://rawg.io/apidocs). Veja /config.\n"
        )
    else:
        console.print()


def run_chat():
    print_banner()
    current_console = None
    games_cache = {}
    last_matches = []
    last_total = 0
    page = 0

    while True:
        label = f"{current_console} " if current_console else ""
        text = questionary.text(f"{label}›").ask()
        if text is None:
            break
        text = text.strip()
        if not text:
            continue

        if text in ("/quit", "/exit", "sair", "exit"):
            break

        if text == "/help":
            console.print(HELP_TEXT)
            continue

        if text == "/consoles":
            for alias, name in sorted(CONSOLE_ALIASES.items()):
                console.print(f"  [cyan]{alias:<14}[/cyan] {name}")
            continue

        if text == "/clear":
            console.clear()
            print_banner()
            continue

        if text == "/back":
            current_console = None
            last_matches, last_total, page = [], 0, 0
            console.print("[dim]Console desmarcado — use /console pra escolher de novo.[/dim]")
            continue

        if text == "/clean":
            clean_partial_downloads()
            continue

        if text == "/top":
            if not current_console:
                console.print("[yellow]Selecione um console primeiro (/console).[/yellow]")
                continue
            curated = _build_top_list(current_console, games_cache)
            if curated is None:
                console.print(
                    "[yellow]Sem RAWG_API_KEY configurada no .env, ou console sem "
                    "mapeamento de plataforma.[/yellow]"
                )
                continue
            if not curated:
                console.print("[yellow]Nenhum dos melhores avaliados foi encontrado no catálogo.[/yellow]")
                continue
            last_matches, last_total = curated, len(curated)
            page = 0
            console.print("[dim]Melhores avaliados (RAWG) disponíveis pra baixar:[/dim]")
            show_page(last_matches, page)
            continue

        if text.startswith("/console"):
            arg = text[len("/console"):].strip()
            picked = resolve_console_name(arg) if arg else pick_console()
            if picked:
                current_console = picked
                last_matches, last_total, page = [], 0, 0
            continue

        if text == "/config":
            from src.settings_screen import run_settings_screen

            run_settings_screen()
            console.print(f"[dim]Pasta de ROMs: {config.ROMS_ROOT}[/dim]")
            continue

        if text.startswith("/root"):
            path = text[len("/root"):].strip()
            if not path:
                console.print("[yellow]Uso: /root <pasta>[/yellow]")
                continue
            set_roms_root(path)
            console.print(f"[green]Pasta raiz de ROMs definida:[/green] {path}")
            continue

        if text in ("/next", "/prev"):
            if not last_matches:
                console.print("[yellow]Nenhuma busca ativa ainda.[/yellow]")
                continue
            page += 1 if text == "/next" else -1
            page = show_page(last_matches, page)
            continue

        if text.startswith("/info"):
            arg = text[len("/info"):].strip()
            if not arg or not last_matches:
                console.print("[yellow]Uso: /info <n> depois de uma busca.[/yellow]")
                continue
            try:
                i = int(arg)
            except ValueError:
                console.print("[yellow]Uso: /info <n> (um número só).[/yellow]")
                continue
            if 1 <= i <= len(last_matches):
                show_game_info(last_matches[i - 1], current_console)
            else:
                console.print(f"[yellow]#{i} fora do intervalo.[/yellow]")
            continue

        if text.startswith("/download"):
            arg = text[len("/download"):].strip()
            if not arg or not last_matches:
                console.print("[yellow]Uso: /download <n>[,<n>...] depois de uma busca.[/yellow]")
                continue
            try:
                indices = [int(x.strip()) for x in arg.replace(",", " ").split()]
            except ValueError:
                console.print("[yellow]Use números separados por vírgula ou espaço.[/yellow]")
                continue
            selected = []
            for i in indices:
                if 1 <= i <= len(last_matches):
                    selected.append(last_matches[i - 1])
                else:
                    console.print(f"[yellow]Ignorando #{i} (fora do intervalo).[/yellow]")
            if selected:
                download_games(selected)
            continue

        if text.startswith("/"):
            console.print(f"[yellow]Comando desconhecido: {text}. /help pra ver a lista.[/yellow]")
            continue

        # Texto puro = busca no console atualmente selecionado.
        if not current_console:
            console.print(
                "[yellow]Nenhum console selecionado. Use [cyan]/console <nome>[/cyan] primeiro.[/yellow]"
            )
            continue

        if current_console not in games_cache:
            games_cache[current_console] = _load_games(current_console)
        games = games_cache[current_console]
        if not games:
            console.print("[red]Nenhum jogo encontrado para esse console.[/red]")
            continue

        last_matches, last_total = search_games(games, text)
        page = 0
        if not last_matches:
            console.print("[yellow]Nenhum resultado.[/yellow]")
            continue
        show_page(last_matches, page)


def main():
    parser = argparse.ArgumentParser(
        prog="roms-downloader",
        description="Busca e baixa ROMs por console, com verificação de integridade.",
    )
    parser.add_argument("--console", help="Nome (ou aproximado) do console")
    parser.add_argument("--query", default="", help="Termo de busca do jogo")
    parser.add_argument("--limit", type=int, default=None, help="Máximo de resultados")
    parser.add_argument(
        "--yes", action="store_true", help="Baixa todos os resultados sem perguntar"
    )
    parser.add_argument(
        "--list-consoles", action="store_true", help="Lista consoles suportados e sai"
    )
    parser.add_argument(
        "--set-root", metavar="PASTA", help="Define e persiste a pasta raiz de ROMs"
    )
    parser.add_argument(
        "--config", action="store_true", help="Abre a tela de configurações e sai"
    )
    parser.add_argument(
        "--clean", action="store_true", help="Lista e apaga downloads incompletos (.partial) e sai"
    )
    args = parser.parse_args()

    if args.clean:
        clean_partial_downloads()
        return

    if args.config:
        from src.settings_screen import run_settings_screen

        run_settings_screen()
        return

    if args.set_root:
        set_roms_root(args.set_root)
        console.print(f"[green]Pasta raiz de ROMs definida:[/green] {args.set_root}")
        return

    if args.list_consoles:
        for name in sorted(CONSOLES_ARCHIVE.keys()):
            console.print(f"- {name}")
        return

    if args.console:
        run_direct(args.console, args.query, args.limit, args.yes)
        return

    run_chat()


if __name__ == "__main__":
    main()
