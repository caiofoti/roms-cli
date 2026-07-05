import logging
import os
import re
import shutil
import sys
import zipfile
from urllib.parse import unquote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_http_session = None


def get_http_session():
    """Sessão HTTP compartilhada com retry automático em falhas transitórias
    (conexão recusada, timeout de conexão, erros 5xx/429)."""
    global _http_session
    if _http_session is None:
        _http_session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "HEAD"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        _http_session.mount("https://", adapter)
        _http_session.mount("http://", adapter)
    return _http_session


ALLOWED_NATIONS = {
    "Japan",
    "USA",
    "Europe",
    "Spain",
    "Italy",
    "Germany",
    "France",
    "China",
}


def extract_nations(game_name):
    """Extrai as regiões do nome do jogo a partir do padrão entre parênteses.
    Ex: "Final Fantasy (Europe, USA)" retorna ["Europe", "USA"]."""
    pattern = r"\((.*?)\)"
    match = re.search(pattern, game_name)
    if match:
        nations_str = match.group(1)
        nations = [s.strip() for s in nations_str.split(",")]
        return [nation for nation in nations if nation in ALLOWED_NATIONS]
    return []


def extract_zip(zip_path, extract_to):
    """
    Extrai o conteúdo do ZIP em zip_path para extract_to.
    Se a extração tiver sucesso, apaga o arquivo ZIP.

    Rejeita entradas que tentam escapar de extract_to (zip slip / path traversal)
    antes de extrair qualquer coisa.
    """
    try:
        safe_root = os.path.realpath(extract_to)
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            for member in zip_ref.namelist():
                dest = os.path.realpath(os.path.join(extract_to, member))
                if dest != safe_root and not dest.startswith(safe_root + os.sep):
                    raise ValueError(f"Entrada de zip insegura (path traversal): {member}")
            zip_ref.extractall(extract_to)
        os.remove(zip_path)
        return True
    except Exception as e:
        logging.error(f"Erro na extração de '{zip_path}': {e}")
        return False


def extract_7z(archive_path, extract_to):
    """
    Extrai o conteúdo do .7z em archive_path para extract_to.
    Se a extração tiver sucesso, apaga o arquivo .7z.

    Rejeita entradas que tentam escapar de extract_to (path traversal)
    antes de extrair qualquer coisa.
    """
    import py7zr

    try:
        safe_root = os.path.realpath(extract_to)
        with py7zr.SevenZipFile(archive_path, mode="r") as archive:
            for member in archive.getnames():
                dest = os.path.realpath(os.path.join(extract_to, member))
                if dest != safe_root and not dest.startswith(safe_root + os.sep):
                    raise ValueError(f"Entrada de 7z insegura (path traversal): {member}")
            archive.extractall(path=extract_to)
        os.remove(archive_path)
        return True
    except Exception as e:
        logging.error(f"Erro na extração de '{archive_path}': {e}")
        return False


def extract_rar(archive_path, extract_to):
    """
    Extrai o conteúdo do .rar em archive_path para extract_to usando patool
    (requer 7z/unrar disponível no sistema).
    Se a extração tiver sucesso, apaga o arquivo .rar.
    """
    import patoolib

    try:
        patoolib.extract_archive(archive_path, outdir=extract_to, interactive=False)
        os.remove(archive_path)
        return True
    except Exception as e:
        logging.error(f"Erro na extração de '{archive_path}': {e}")
        return False


ARCHIVE_EXTRACTORS = {
    ".zip": extract_zip,
    ".7z": extract_7z,
    ".rar": extract_rar,
}


def extract_archive(archive_path, extract_to):
    """
    Extrai o arquivo compactado (.zip/.7z/.rar) deixando o jogo pronto pra jogar,
    sem precisar descompactar manualmente depois do download.
    Retorna True se extraiu (ou se a extensão não é um arquivo compactado
    conhecido, ex: .iso/.chd que já rodam direto), False se a extração falhou.
    """
    ext = os.path.splitext(archive_path)[1].lower()
    extractor = ARCHIVE_EXTRACTORS.get(ext)
    if extractor is None:
        return True
    return extractor(archive_path, extract_to)


def find_retroarch():
    """Localiza o executável do RetroArch: primeiro no PATH do sistema,
    depois em locais comuns de instalação por SO. Retorna o caminho absoluto
    ou None se não encontrado."""
    path_in_syspath = shutil.which("retroarch")
    if path_in_syspath and os.path.exists(path_in_syspath):
        logging.info(f"RetroArch encontrado no PATH: {path_in_syspath}")
        return path_in_syspath

    possible = []
    if sys.platform.startswith("win"):
        possible = [
            r"C:\RetroArch-Win64\retroarch.exe",
            r"C:\Program Files\RetroArch\retroarch.exe",
            r"C:\Program Files (x86)\RetroArch\retroarch.exe",
        ]
    elif sys.platform.startswith("linux"):
        possible = ["/usr/bin/retroarch", "/usr/local/bin/retroarch"]
    elif sys.platform.startswith("darwin"):
        possible = ["/Applications/RetroArch.app/Contents/MacOS/retroarch"]

    for p in possible:
        if os.path.exists(p):
            logging.info(f"RetroArch encontrado em local comum: {p}")
            return p

    logging.warning("RetroArch não encontrado no PATH nem em locais comuns de instalação.")
    return None


def clean_rom_title(filename):
    """Limpa o nome do arquivo ROM removendo tags comuns, extensão, etc."""
    if not filename:
        return ""

    try:
        name_decoded = unquote(filename)
    except Exception as e:
        logging.warning(f"Erro ao decodificar URL de '{filename}': {e}")
        name_decoded = filename

    name_without_ext, _ = os.path.splitext(name_decoded)

    cleaned = name_without_ext
    logging.debug(f"Limpeza de título: início com '{cleaned}'")

    patterns_to_remove = [
        # 1. Tag Dump/Info entre colchetes (geralmente no início ou fim)
        r"^\s*\[.*?\]\s*",
        r"\s*\[.*?\]\s*$",
        # 2. Tag Revisão/Versão
        r"\s*\((?:Rev|v|Version|Ver)\s*[\w\.]+\)\s*",
        # 3. Tag Beta/Proto/Demo/Etc.
        r"\s*\((?:Beta|Proto|Sample|Demo|Pre-Release|Promo|Test)\w*\)\s*",
        # 4. Tag Região/Idioma
        r"\s*\(\s*(\b(?:USA|Europe|World|Japan|France|Germany|Spain|Italy|Korea|China|Australia|Brazil|Netherlands|Sweden|Denmark|Finland|Russia|En|Fr|De|Es|It|Ja|Ko|Zh|Nl|Pt|Sv|No|Da|Fi|Ru|Pl|Cz|Hu|Tr)\b\s*,?\s*)+\)\s*",
        # 5. Tag Disco/Faixa
        r"\s*\(Disc\s*\d+(?:-\d+)?\s*(?:of\s*\d+)?\)\s*",
        r"\s*\(Track\s*\d+\)\s*",
        r"\s*\((?:Bonus|Soundtrack|Demo)\s*Disc\)\s*",
        # 6. Tags específicas (NDSi Enhanced, etc.)
        r"\s*\((?:NDSi Enhanced|DSi Enhanced|GBC Enhanced|SGB Enhanced)\)\s*",
        r"\s*\((?:Unl|Pirate|Hack|Translated|Public Domain|PD|Homebrew)\w*\)\s*",
        r"\s*\((?:Alt|Sample|Remaster|Remix)\w*\)\s*",
        # 7. Parênteses com datas (ex: YYYY-MM-DD ou ano) no fim
        r"\s*\(\s*\d{4}(?:-\d{2}-\d{2})?\s*\)\s*$",
        # 8. Remove (tm), (r) no fim das palavras
        r"\b(?:™|\(tm\)|\(r\)|®)\b",
        # 9. Remove parênteses/colchetes vazios ou só com espaços, que sobraram
        r"\s*\(+\s*\)+\s*",
        r"\s*\[+\s*\]+\s*",
    ]

    previous_cleaned = ""
    loops = 0
    while previous_cleaned != cleaned and loops < 10:
        previous_cleaned = cleaned
        for pattern in patterns_to_remove:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = " ".join(cleaned.split()).strip()
        cleaned = re.sub(r"^[_\-\s]+|[_\-\s]+$", "", cleaned).strip()
        loops += 1

    logging.debug(f"Limpeza de título: resultado final '{cleaned}'")

    return cleaned if cleaned else name_without_ext
