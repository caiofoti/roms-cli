import logging
import os
import re
import sys

import requests

from src.utils import find_retroarch

PCSX2_COVERS_FOLDER = os.path.join(
    os.path.expanduser("~"), "Documents", "PCSX2", "covers"
)

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
    """RetroArch guarda config/thumbnails ao lado do executável só na
    instalação portátil (comum no Windows). Instalação nativa no Linux
    (~/.config/retroarch) e no macOS (~/Library/Application Support/RetroArch)
    guarda em outro lugar — testa o padrão do SO primeiro, cai pro lado do
    executável se não existir (cobre instalação portátil em qualquer SO)."""
    if sys.platform.startswith("linux"):
        candidate_root = os.path.join(os.path.expanduser("~"), ".config", "retroarch")
        if os.path.isdir(candidate_root):
            return os.path.join(candidate_root, "thumbnails")
    elif sys.platform.startswith("darwin"):
        candidate_root = os.path.join(
            os.path.expanduser("~"), "Library", "Application Support", "RetroArch"
        )
        if os.path.isdir(candidate_root):
            return os.path.join(candidate_root, "thumbnails")

    exe = find_retroarch()
    if not exe:
        return None
    return os.path.join(os.path.dirname(exe), "thumbnails")


_COVER_EXTS = (".jpg", ".jpeg", ".png")


def _cover_base_paths(game_title, console_name):
    """Caminho (sem extensão) de onde a capa de cada emulador vai/já está,
    pra download/checagem/remoção usarem o mesmo cálculo. Chave ausente do
    dict = esse emulador não se aplica (console errado ou não encontrado)."""
    bases = {}
    if console_name == "Sony PlayStation 2 (PS2)":
        bases["pcsx2"] = os.path.join(
            PCSX2_COVERS_FOLDER, sanitize_filename(game_title)
        )

    system_dir = RETROARCH_THUMB_SYSTEM_DIRS.get(console_name)
    thumbs_root = _retroarch_thumbnails_root()
    if system_dir and thumbs_root:
        bases["retroarch"] = os.path.join(
            thumbs_root,
            system_dir,
            "Named_Boxarts",
            _sanitize_retroarch_thumb_name(game_title),
        )

    return bases


def covers_exist(game_title, console_name):
    """Diz se a capa já foi salva antes pra esse jogo, sem baixar nada —
    usado pelo /scan pra não gastar chamada RAWG em jogo que já tem capa."""
    result = {"pcsx2": False, "retroarch": False}
    for key, base in _cover_base_paths(game_title, console_name).items():
        result[key] = any(os.path.exists(base + ext) for ext in _COVER_EXTS)
    return result


def delete_covers(game_title, console_name):
    """Apaga as capas salvas (PCSX2/RetroArch) associadas ao título, se existirem."""
    for base in _cover_base_paths(game_title, console_name).values():
        for ext in _COVER_EXTS:
            path = base + ext
            if os.path.exists(path):
                os.remove(path)


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
    if ext not in _COVER_EXTS:
        ext = ".jpg"

    for key, base in _cover_base_paths(game_title, console_name).items():
        try:
            os.makedirs(os.path.dirname(base), exist_ok=True)
            with open(f"{base}{ext}", "wb") as f:
                f.write(image_bytes)
            result[key] = True
        except OSError as e:
            logging.error(f"Erro ao salvar capa ({key}) de '{game_title}': {e}")

    return result
