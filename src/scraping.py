import json
import logging
import os

import requests
from thefuzz import fuzz

from src import db
from src.config import BASE_URL, CONSOLES_ARCHIVE
from src.mapping import apply_title_term_map, simplify_title
from src.utils import clean_rom_title, get_http_session

ROM_EXTENSIONS = {
    ".zip",
    ".7z",
    ".rar",
    ".iso",
    ".chd",
    ".cue",
    ".bin",
    ".gba",
    ".gb",
    ".gbc",
    ".nes",
    ".sfc",
    ".smc",
    ".n64",
    ".z64",
    ".v64",
    ".nds",
    ".gg",
    ".md",
    ".sms",
    ".pbp",
    ".cso",
}


def format_size(size_bytes):
    try:
        size_bytes = int(size_bytes)
    except (TypeError, ValueError):
        return "? MB"
    if size_bytes >= 1024**3:
        return f"{size_bytes / 1024**3:.2f} GiB"
    elif size_bytes >= 1024**2:
        return f"{size_bytes / 1024**2:.2f} MiB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.2f} KiB"
    return f"{size_bytes} B"


def parse_size_string(size_str):
    try:
        parts = size_str.split()
        if len(parts) >= 2:
            value = float(parts[0].replace(",", "."))
            unit = parts[1].lower()
            if unit.startswith("gib"):
                return int(value * 1024**3)
            elif unit.startswith("gb"):
                return int(value * 1000**3)
            elif unit.startswith("mib"):
                return int(value * 1024 * 1024)
            elif unit.startswith("mb"):
                return int(value * 1000 * 1000)
            elif unit.startswith("kib"):
                return int(value * 1024)
            elif unit.startswith("kb"):
                return int(value * 1000)
            else:
                return int(value)
        return 0
    except Exception as e:
        logging.error(f"Erro ao analisar tamanho '{size_str}': {e}")
        return 0


def get_archive_item_stats(identifier):
    """Busca downloads/avaliação do item no archive.org via advancedsearch.

    São métricas do item/coleção inteira (ex: 'redump_ps2'), não por ROM
    individual — o archive.org não expõe estatística por arquivo dentro de
    uma coleção. Ainda assim servem como sinal de confiabilidade da fonte:
    quantas pessoas já baixaram esse mesmo acervo e como avaliaram.
    """
    url = "https://archive.org/advancedsearch.php"
    params = {
        "q": f"identifier:{identifier}",
        "fl[]": ["downloads", "avg_rating", "num_reviews"],
        "output": "json",
    }
    try:
        response = get_http_session().get(url, params=params, timeout=15)
        response.raise_for_status()
        docs = response.json().get("response", {}).get("docs", [])
        if docs:
            doc = docs[0]
            return {
                "downloads": doc.get("downloads"),
                "avg_rating": doc.get("avg_rating"),
                "num_reviews": doc.get("num_reviews"),
            }
    except Exception as e:
        logging.error(
            f"Erro ao buscar estatísticas do archive.org para '{identifier}': {e}"
        )
    return {"downloads": None, "avg_rating": None, "num_reviews": None}


def get_games_for_console(console_name):
    """Busca lista de jogos via API do archive.org para o console especificado."""
    console_data = CONSOLES_ARCHIVE.get(console_name)
    if not console_data:
        logging.error(f"Console '{console_name}' não encontrado em CONSOLES_ARCHIVE.")
        return []

    _folder, identifiers = console_data
    games = []
    seen_names = set()

    for identifier in identifiers:
        url = f"https://archive.org/metadata/{identifier}/files"
        logging.info(f"Buscando jogos de '{console_name}' em: {identifier}")
        try:
            response = get_http_session().get(url, timeout=30)
            response.raise_for_status()
            data = response.json()
            files = data.get("result", [])
        except Exception as e:
            logging.error(f"Erro ao buscar '{identifier}': {e}")
            continue

        archive_stats = get_archive_item_stats(identifier)

        for f in files:
            filename = f.get("name", "")
            ext = os.path.splitext(filename)[1].lower()
            if ext not in ROM_EXTENSIONS:
                continue

            # O "name" do archive.org pode incluir subpastas (ex: "PlayStation 2/Jogo.zip");
            # usamos só o nome do arquivo pra busca/exibição não ficar poluída, mas o link
            # de download preserva o caminho completo.
            name = os.path.splitext(os.path.basename(filename))[0]
            if name in seen_names:
                continue
            seen_names.add(name)

            size_bytes = int(f.get("size", 0) or 0)
            size_str = format_size(size_bytes)
            from urllib.parse import quote

            encoded_filename = quote(filename, safe="/")
            link = f"{BASE_URL}{identifier}/{encoded_filename}"

            games.append(
                {
                    "name": name,
                    "link": link,
                    "size_bytes": size_bytes,
                    "size_str": size_str,
                    "console": console_name,
                    "folder": _folder,
                    "md5": f.get("md5"),
                    "sha1": f.get("sha1"),
                    "archive_downloads": archive_stats["downloads"],
                    "archive_rating": archive_stats["avg_rating"],
                    "archive_reviews": archive_stats["num_reviews"],
                }
            )

        logging.info(f"  {identifier}: {len(games)} jogos acumulados")

    logging.info(f"Total para '{console_name}': {len(games)} jogos")
    return games


def get_games_for_console_cached(console_name):
    """Catálogo persistido em SQLite (src/db.py) — sobrevive entre execuções
    sem depender de um arquivo JSON solto que dá pra apagar sem querer."""
    cached = db.load_catalog(console_name)
    if cached is not None:
        logging.info(
            f"Cache (SQLite) carregada para console '{console_name}': {len(cached)} jogos"
        )
        return cached

    games = get_games_for_console(console_name)
    if games:
        db.save_catalog(console_name, games)
        logging.info(
            f"Cache (SQLite) salva para console '{console_name}': {len(games)} jogos"
        )
    return games


class GameApiClient:
    def __init__(self):
        self.rawg_api_key = os.getenv("RAWG_API_KEY")

        if not self.rawg_api_key:
            logging.warning(
                "API Key RAWG não encontrada nas variáveis de ambiente. As buscas RAWG vão falhar."
            )

    def search_rawg(self, title, platform_name=None):
        if not self.rawg_api_key:
            return None

        base_url = "https://api.rawg.io/api/games"
        platform_id = RAWG_PLATFORM_MAP.get(platform_name)
        params = {"key": self.rawg_api_key, "search": title, "page_size": 1}
        if platform_id:
            params["platforms"] = platform_id
        else:
            logging.warning(
                f"[RAWG] ID de plataforma não encontrado para '{platform_name}', buscando sem filtro de plataforma."
            )

        try:
            response = requests.get(base_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            if data and data.get("results"):
                game = data["results"][0]
                logging.info(
                    f"[RAWG] Resultado encontrado para '{title}': {game.get('name')}"
                )

                release_date_str = game.get("released")
                genres = [
                    g.get("name") for g in game.get("genres", []) if g.get("name")
                ]
                cover_url = game.get("background_image")
                description = f"Descrição não obtida do RAWG (precisa de chamada adicional ao ID: {game.get('id')})"

                metacritic = game.get("metacritic")
                rawg_rating = game.get("rating")  # escala 0-5
                if metacritic:
                    rating_100 = metacritic
                elif rawg_rating:
                    rating_100 = round(rawg_rating * 20)
                else:
                    rating_100 = None

                return {
                    "api_source": "RAWG",
                    "api_title": game.get("name"),
                    "description": description,
                    "release_date": release_date_str,
                    "genres": genres,
                    "languages": [],
                    "cover_url": cover_url,
                    "rating_100": rating_100,
                }
            else:
                logging.info(f"[RAWG] Nenhum resultado para '{title}'")
                return None

        except requests.exceptions.RequestException as e:
            logging.error(f"Erro na requisição RAWG para '{title}': {e}")
            return None
        except json.JSONDecodeError:
            logging.error(
                f"Erro ao decodificar resposta JSON do RAWG para '{title}': {response.text}"
            )
            return None


def fetch_top_rated_titles(console_name, limit=30):
    """Busca os jogos mais bem avaliados (RAWG) pra uma plataforma. Retorna
    [{"name": ..., "rating_100": ...}], só os que têm nota real (metacritic ou
    nota de usuário), ordenados por nota desc."""
    api_client = get_api_client()
    platform_id = RAWG_PLATFORM_MAP.get(console_name)
    if not platform_id or not api_client.rawg_api_key:
        return []

    params = {
        "key": api_client.rawg_api_key,
        "platforms": platform_id,
        "ordering": "-metacritic",
        "page_size": limit,
    }
    try:
        response = get_http_session().get(
            "https://api.rawg.io/api/games", params=params, timeout=15
        )
        response.raise_for_status()
        results = response.json().get("results", [])
    except requests.exceptions.RequestException as e:
        logging.error(
            f"Erro ao buscar melhores jogos (RAWG) para '{console_name}': {e}"
        )
        return []

    titles = []
    for g in results:
        metacritic = g.get("metacritic")
        rating = g.get("rating")
        rating_100 = metacritic or (round(rating * 20) if rating else None)
        if rating_100 is not None:
            titles.append({"name": g.get("name"), "rating_100": rating_100})

    titles.sort(key=lambda t: t["rating_100"], reverse=True)
    return titles


_game_api_client_instance = None


def get_api_client():
    """Instancia o cliente na primeira chamada real (não no import do módulo).
    RAWG_API_KEY é lida do ambiente só nesse momento — importar scraping.py
    antes do .env ser carregado (ex: entry point instalado via pip/pipx, que
    não passa por run.py) não trava mais a chave como 'ausente' pra sempre."""
    global _game_api_client_instance
    if _game_api_client_instance is None:
        _game_api_client_instance = GameApiClient()
    return _game_api_client_instance


def fetch_game_details(original_filename, console_name):
    if not original_filename:
        return None

    cleaned_title = clean_rom_title(original_filename)
    if not cleaned_title:
        logging.warning(f"[API Fetch] Título limpo vazio para '{original_filename}'")
        return None

    logging.info(
        f"[API Fetch] Iniciando busca para '{original_filename}' -> Limpo: '{cleaned_title}'"
    )

    search_attempts = []
    search_attempts.append(cleaned_title)
    mapped_title = apply_title_term_map(cleaned_title)
    if mapped_title.lower() != cleaned_title.lower():
        search_attempts.append(mapped_title)
    simplified = simplify_title(cleaned_title)
    if simplified != cleaned_title and simplified.lower() not in [
        t.lower() for t in search_attempts
    ]:
        search_attempts.append(simplified)
    if " - " in cleaned_title:
        base_title = cleaned_title.split(" - ")[0].strip()
        if base_title != cleaned_title and base_title.lower() not in [
            t.lower() for t in search_attempts
        ]:
            search_attempts.append(base_title)

    seen = set()
    unique_attempts = []
    for item in search_attempts:
        lowered = item.lower()
        if lowered not in seen:
            seen.add(lowered)
            unique_attempts.append(item)

    logging.debug(f"[API Fetch] Tentativas de busca ordenadas: {unique_attempts}")

    MIN_SIMILARITY_THRESHOLD = 80

    for attempt_title in unique_attempts:
        logging.debug(
            f"[API Fetch] Tentativa RAWG com '{attempt_title}' (Console: {console_name})..."
        )
        rawg_details = get_api_client().search_rawg(attempt_title, console_name)
        if rawg_details:
            api_title = rawg_details.get("api_title", "")
            similarity_score = fuzz.token_set_ratio(
                attempt_title.lower(), api_title.lower()
            )
            logging.debug(
                f"[API Validation RAWG] Comparando: '{attempt_title}' vs API '{api_title}' -> Score: {similarity_score}"
            )
            if similarity_score >= MIN_SIMILARITY_THRESHOLD:
                logging.info(
                    f"[API Fetch] SUCESSO (RAWG): Encontrado '{api_title}' com score {similarity_score} >= {MIN_SIMILARITY_THRESHOLD}"
                )
                return rawg_details
            else:
                logging.warning(
                    f"[API Fetch] RESULTADO DESCARTADO (RAWG): API encontrou '{api_title}', mas similaridade ({similarity_score}) baixa demais em relação a '{attempt_title}'."
                )

    logging.warning(
        f"[API Fetch] FALHA TOTAL: Nenhum resultado válido encontrado para '{original_filename}' após todas as tentativas e validações."
    )
    return None


RAWG_PLATFORM_MAP = {
    "Game Boy (GB)": 26,
    "Game Boy Color (GBC)": 43,
    "Game Boy Advance (GBA)": 24,
    "Nintendo (NES/Famicom)": 49,
    "Super Nintendo (SNES)": 79,
    "Nintendo 64 (N64)": 83,
    "Nintendo DS (NDS)": 9,
    "Sega Master System": 74,
    "Sega Game Gear": 77,
    "Sega Genesis/Mega Drive": 167,
    "Sony PlayStation (PSX)": 27,
    "Sony PlayStation 2 (PS2)": 15,
    "Sony PSP": 17,
    "Sega Dreamcast": 106,
}
