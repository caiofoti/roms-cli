import logging
import os

import questionary

from src import config
from src.config import CONSOLES_ARCHIVE, set_roms_root
from src.display import console, pick_games, show_page, show_results
from src.downloader import clean_partial_downloads, download_games
from src.scraping import get_games_for_console_cached
from src.search import CONSOLE_ALIASES, pick_console, resolve_console_name, search_games


def _load_games(console_name):
    with console.status(f"Carregando catálogo de {console_name}..."):
        try:
            return get_games_for_console_cached(console_name)
        except Exception as e:
            logging.error(f"Erro ao carregar catálogo: {e}")
            return []


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
