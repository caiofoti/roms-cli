import json
import logging
import os

try:
    import platformdirs
except ImportError:
    print("Erro: a biblioteca 'platformdirs' não está instalada.")
    print("Rode: pip install platformdirs")
    platformdirs = None

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

APP_NAME = "RomsDownloader"
AUTHOR_NAME = "YourAppNameOrCompany"

if platformdirs:
    USER_DATA_DIR = platformdirs.user_data_dir(APP_NAME, AUTHOR_NAME)
    USER_CONFIG_DIR = platformdirs.user_config_dir(APP_NAME, AUTHOR_NAME)
    USER_CACHE_DIR = platformdirs.user_cache_dir(APP_NAME, AUTHOR_NAME)
else:
    USER_DATA_DIR = os.path.join(os.path.expanduser("~"), ".local", "share", APP_NAME)
    USER_CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", APP_NAME)
    USER_CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache", APP_NAME)

DATA_DIR = USER_DATA_DIR
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR, exist_ok=True)


class _JsonSettings:
    """Armazenamento simples de configurações em JSON."""

    def __init__(self, path):
        self._path = path
        self._data = {}
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except Exception as e:
                logging.error(f"Erro ao carregar configurações '{path}': {e}")

    def value(self, key, default=None):
        return self._data.get(key, default)

    def setValue(self, key, value):
        self._data[key] = value
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error(f"Erro ao salvar configurações '{self._path}': {e}")


settings = _JsonSettings(os.path.join(USER_CONFIG_DIR, "settings.json"))

DEFAULT_DOWNLOADS_FOLDER = os.path.join(DATA_DIR, "downloads")

CACHE_FOLDER = USER_CACHE_DIR
if not os.path.exists(CACHE_FOLDER):
    os.makedirs(CACHE_FOLDER, exist_ok=True)

BASE_URL = "https://archive.org/download/"

# Mapeamento: nome do console -> (pasta dentro de ROMS_ROOT, identificadores archive.org)
CONSOLES_ARCHIVE = {
    "Game Boy (GB)": ("gb", ["No-Intro_GB"]),
    "Game Boy Color (GBC)": ("gbc", ["No-Intro_GBC"]),
    "Game Boy Advance (GBA)": ("gba", ["ef_gba_no-intro_2024-02-21"]),
    "Nintendo (NES/Famicom)": ("nes", ["No-Intro_NES"]),
    "Super Nintendo (SNES)": ("snes", ["ef_nintendo_snes_no-intro_2024-04-20"]),
    "Nintendo 64 (N64)": ("n64", ["ef_nintendo_64_no-intro_2024-02-10"]),
    "Nintendo DS (NDS)": ("nds", ["ndsdecryptednointromyrientbackup"]),
    "Sega Master System": ("mastersystem", ["No-Intro_SMS"]),
    "Sega Game Gear": ("gamegear", ["ef_sega_game_gear_no-intro_2024-02-21"]),
    "Sega Genesis/Mega Drive": ("megadrive", ["ni-se-md"]),
    "Sony PlayStation (PSX)": ("psx", ["RedumpSonyPlayStationAmerica20160617"]),
    "Sony PlayStation 2 (PS2)": ("ps2", ["redump_ps2"]),
    "Sega Dreamcast": ("dreamcast", ["sega-dreamcast-redump-collection"]),
    "Sony PSP": (
        "psp",
        [
            "sony_playstation_portable_part1",
            "sony_playstation_portable_part2",
            "sony_playstation_portable_part3",
            "sony_playstation_portable_part4",
        ],
    ),
}

# Compatibilidade com o resto do código (dropdown usa CONSOLES.keys())
CONSOLES = {name: data[0] for name, data in CONSOLES_ARCHIVE.items()}

# Raiz onde ficam as pastas de ROMs (uma por console), pra qualquer emulador
# apontar direto pra elas (RetroArch, PCSX2, etc.).
ROMS_ROOT = settings.value("roms_root", DEFAULT_DOWNLOADS_FOLDER)


def set_roms_root(path):
    """Define e persiste a pasta raiz de ROMs, criando-a se não existir."""
    global ROMS_ROOT
    ROMS_ROOT = path
    os.makedirs(ROMS_ROOT, exist_ok=True)
    settings.setValue("roms_root", ROMS_ROOT)
    ensure_all_console_folders()


def ensure_all_console_folders():
    """Cria a pasta de cada console dentro de ROMS_ROOT, mesmo sem download
    ainda, pra qualquer emulador já encontrar a estrutura pronta.

    Se ROMS_ROOT estiver num drive desconectado (ex: HD externo), cai de volta
    pra pasta local de downloads em vez de derrubar o programa inteiro.
    """
    global ROMS_ROOT
    try:
        for _name, (folder, _ids) in CONSOLES_ARCHIVE.items():
            os.makedirs(os.path.join(ROMS_ROOT, folder), exist_ok=True)
    except OSError as e:
        logging.error(
            f"Não foi possível acessar/criar pastas em ROMS_ROOT '{ROMS_ROOT}' "
            f"(drive desconectado?): {e}. Usando pasta local de fallback: "
            f"{DEFAULT_DOWNLOADS_FOLDER}"
        )
        ROMS_ROOT = DEFAULT_DOWNLOADS_FOLDER
        for _name, (folder, _ids) in CONSOLES_ARCHIVE.items():
            os.makedirs(os.path.join(ROMS_ROOT, folder), exist_ok=True)


ensure_all_console_folders()

# Parâmetros de busca, editáveis pela tela de configurações (/config no chat).
DEFAULT_RESULT_LIMIT = int(settings.value("default_limit", 25))
MIN_SIMILARITY = int(settings.value("min_similarity", 40))


def set_default_result_limit(value):
    global DEFAULT_RESULT_LIMIT
    DEFAULT_RESULT_LIMIT = int(value)
    settings.setValue("default_limit", DEFAULT_RESULT_LIMIT)


def set_min_similarity(value):
    global MIN_SIMILARITY
    MIN_SIMILARITY = int(value)
    settings.setValue("min_similarity", MIN_SIMILARITY)


MAX_CONCURRENT_DOWNLOADS = int(settings.value("max_concurrent_downloads", 3))


def set_max_concurrent_downloads(value):
    global MAX_CONCURRENT_DOWNLOADS
    value = int(value)
    if not (1 <= value <= 10):
        raise ValueError("Downloads simultâneos deve ser entre 1 e 10.")
    MAX_CONCURRENT_DOWNLOADS = value
    settings.setValue("max_concurrent_downloads", MAX_CONCURRENT_DOWNLOADS)


# 0 = desligado. Limpa a tela do chat sozinho a cada N ações (busca/download/
# delete), pra não virar um scroll infinito em sessões longas.
AUTO_CLEAR_AFTER = int(settings.value("auto_clear_after", 0))


def set_auto_clear_after(value):
    global AUTO_CLEAR_AFTER
    value = int(value)
    if value < 0:
        raise ValueError("Auto-clear deve ser 0 (desligado) ou um número positivo.")
    AUTO_CLEAR_AFTER = value
    settings.setValue("auto_clear_after", AUTO_CLEAR_AFTER)
