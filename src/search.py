import questionary
from thefuzz import fuzz

from src import config
from src.config import CONSOLES_ARCHIVE

CONSOLE_ALIASES = {
    folder.lower(): name for name, (folder, _ids) in CONSOLES_ARCHIVE.items()
}


def pick_console():
    return questionary.select("Console:", choices=sorted(CONSOLES_ARCHIVE.keys())).ask()


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
    relevância (score desc) e, em empate, por tamanho do nome (mais curto/direto primeiro).
    """
    limit = limit or config.DEFAULT_RESULT_LIMIT
    if not query:
        ordered = sorted(games, key=lambda g: g["name"].lower())
        return ordered[:limit], len(ordered)

    query_l = query.lower()
    scored = [(g, _match_score(query_l, g["name"].lower())) for g in games]
    scored = [(g, s) for g, s in scored if s >= config.MIN_SIMILARITY]
    scored.sort(key=lambda pair: (-pair[1], len(pair[0]["name"])))
    return [g for g, _ in scored[:limit]], len(scored)
