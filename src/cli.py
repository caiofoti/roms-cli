import argparse

from src.config import CONSOLES_ARCHIVE, set_roms_root
from src.display import console
from src.downloader import clean_partial_downloads
from src.repl import run_chat, run_direct


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
        "--clean",
        action="store_true",
        help="Lista e apaga downloads incompletos (.partial) e sai",
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
