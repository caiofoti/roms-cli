import sys

import questionary
from rich.console import Console
from rich.table import Table

# Console do Windows sem UTF-8 (cp1252 é o padrão do cmd.exe) quebra em
# acentos e em '★' — força UTF-8 aqui, antes do Console() ser criado, pra
# funcionar em qualquer terminal (run.py e o entry point instalado via pip
# passam por este módulo antes de imprimir algo).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

console = Console()

PAGE_SIZE = 10


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
    page_items = matches[start : start + PAGE_SIZE]

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
        questionary.Choice(f"{g['name']}  [{g['size_str']}]", value=g) for g in matches
    ]
    return (
        questionary.checkbox(
            "Selecione (espaço) e confirme (enter):", choices=choices
        ).ask()
        or []
    )
