import os

from src import config
from src.config import CONSOLES_ARCHIVE

FOLDER_TO_CONSOLE = {folder: name for name, (folder, _ids) in CONSOLES_ARCHIVE.items()}


def scan_library():
    """Varre ROMS_ROOT inteiro (todas as pastas de console) e busca capa
    (RAWG) pra qualquer ROM que ainda não tenha uma salva — cobre jogos
    colocados manualmente na pasta ou baixados antes dessa função existir.

    Retorna (total_de_roms_encontradas, total_de_capas_novas_salvas).
    """
    from src.metadata_manager import covers_exist, download_covers_for_emulators
    from src.scraping import fetch_game_details

    total = 0
    saved = 0

    for folder, console_name in FOLDER_TO_CONSOLE.items():
        dest_dir = os.path.join(config.ROMS_ROOT, folder)
        if not os.path.isdir(dest_dir):
            continue

        for fname in os.listdir(dest_dir):
            path = os.path.join(dest_dir, fname)
            if not os.path.isfile(path) or fname.endswith(".partial"):
                continue

            total += 1
            title = os.path.splitext(fname)[0]

            if any(covers_exist(title, console_name).values()):
                continue

            details = fetch_game_details(title, console_name)
            if not details or not details.get("cover_url"):
                continue

            result = download_covers_for_emulators(
                details["cover_url"], title, console_name
            )
            if any(result.values()):
                saved += 1

    return total, saved
