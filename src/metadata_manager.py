import logging
import os
import re

import requests

from src.utils import find_retroarch

PCSX2_COVERS_FOLDER = os.path.join(os.path.expanduser("~"), "Documents", "PCSX2", "covers")

# Nome exato da pasta de sistema usada pelo repositório oficial de thumbnails
# do RetroArch (libretro-thumbnails) — precisa bater com isso pra aparecer.
RETROARCH_THUMB_SYSTEM_DIRS = {
    "Game Boy (GB)": "Nintendo - Game Boy",
    "Game Boy Color (GBC)": "Nintendo - Game Boy Color",
    "Game Boy Advance (GBA)": "Nintendo - Game Boy Advance",
    "Nintendo (NES/Famicom)": "Nintendo - Nintendo Entertainment System",
    "Super Nintendo (SNES)": "Nintendo - Super Nintendo Entertainment System",
    "Nintendo 64 (N64)": "Nintendo - Nintendo 64",
    "Nintendo DS (NDS)": "Nintendo - Nintendo DS",
    "Sega Master System": "Sega - Master System - Mark III",
    "Sega Game Gear": "Sega - Game Gear",
    "Sega Genesis/Mega Drive": "Sega - Mega Drive - Genesis",
    "Sony PlayStation (PSX)": "Sony - PlayStation",
    "Sony PlayStation 2 (PS2)": "Sony - PlayStation 2",
    "Sega Dreamcast": "Sega - Dreamcast",
    "Sony PSP": "Sony - PlayStation Portable",
}


def sanitize_filename(filename):
    """Remove/substitui caracteres inválidos em nomes de arquivo."""
    sanitized = re.sub(r'[\\/*?:"<>|]', "_", filename)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    max_len = 100
    if len(sanitized) > max_len:
        name, ext = os.path.splitext(sanitized)
        sanitized = name[: max_len - len(ext)] + ext
    return sanitized


def _sanitize_retroarch_thumb_name(title):
    """RetroArch exige que o nome do arquivo de thumbnail bata com o label
    exibido na playlist: '&' vira '_', e caracteres inválidos de path saem."""
    name = title.replace("&", "_")
    for ch in '*/:`<>?\\|"':
        name = name.replace(ch, "")
    return name.strip()


def _retroarch_thumbnails_root():
    exe = find_retroarch()
    if not exe:
        return None
    return os.path.join(os.path.dirname(exe), "thumbnails")


def download_covers_for_emulators(cover_url, game_title, console_name):
    """
    Baixa a capa uma única vez e distribui pro formato/local que cada emulador
    espera, deixando a capa pronta pra aparecer sem passo manual:
      - PCSX2: Documents/PCSX2/covers/<título>.<ext> (casa por título na lista)
      - RetroArch: thumbnails/<Sistema>/Named_Boxarts/<título saneado>.<ext>
        (casa pelo label da entrada na playlist; pulado se RetroArch não
        estiver instalado/encontrado)

    Retorna dict {"pcsx2": bool, "retroarch": bool} indicando onde salvou.
    """
    result = {"pcsx2": False, "retroarch": False}
    if not cover_url or not game_title:
        return result

    try:
        response = requests.get(cover_url, timeout=20)
        response.raise_for_status()
        image_bytes = response.content
    except Exception as e:
        logging.error(f"Erro ao baixar capa de '{cover_url}': {e}")
        return result

    ext = os.path.splitext(cover_url.split("?")[0])[-1].lower()
    if ext not in (".jpg", ".jpeg", ".png"):
        ext = ".jpg"

    if console_name == "Sony PlayStation 2 (PS2)":
        try:
            os.makedirs(PCSX2_COVERS_FOLDER, exist_ok=True)
            path = os.path.join(PCSX2_COVERS_FOLDER, f"{sanitize_filename(game_title)}{ext}")
            with open(path, "wb") as f:
                f.write(image_bytes)
            result["pcsx2"] = True
        except OSError as e:
            logging.error(f"Erro ao salvar capa PCSX2 de '{game_title}': {e}")

    system_dir = RETROARCH_THUMB_SYSTEM_DIRS.get(console_name)
    thumbs_root = _retroarch_thumbnails_root()
    if system_dir and thumbs_root:
        try:
            dest_dir = os.path.join(thumbs_root, system_dir, "Named_Boxarts")
            os.makedirs(dest_dir, exist_ok=True)
            safe_title = _sanitize_retroarch_thumb_name(game_title)
            path = os.path.join(dest_dir, f"{safe_title}{ext}")
            with open(path, "wb") as f:
                f.write(image_bytes)
            result["retroarch"] = True
        except OSError as e:
            logging.error(f"Erro ao salvar thumbnail RetroArch de '{game_title}': {e}")

    return result
