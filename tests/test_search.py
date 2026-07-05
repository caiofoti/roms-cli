from src.search import _match_score, resolve_console_name, search_games


def test_match_score_exact_substring_wins():
    assert _match_score("crash", "crash bandicoot") == 100


def test_match_score_discriminates_different_titles():
    # Regressão real: WRatio empatava "God of War" com "Crash Bandicoot"
    # numa busca por "crash". token_set_ratio não pode repetir isso.
    score_correct = _match_score("crash", "crash bandicoot - the wrath of cortex")
    score_wrong = _match_score("crash", "god of war")
    assert score_correct > score_wrong


def test_search_games_filters_by_min_similarity(monkeypatch):
    import src.config as config

    monkeypatch.setattr(config, "MIN_SIMILARITY", 90)
    games = [
        {"name": "Crash Bandicoot", "size_str": "1 GiB"},
        {"name": "Completely Unrelated Title", "size_str": "1 GiB"},
    ]
    matches, total = search_games(games, "Crash Bandicoot")
    assert total == 1
    assert matches[0]["name"] == "Crash Bandicoot"


def test_search_games_empty_query_sorts_alphabetically():
    games = [{"name": "Zelda", "size_str": "1"}, {"name": "Adventure", "size_str": "1"}]
    matches, total = search_games(games, "")
    assert total == 2
    assert [g["name"] for g in matches] == ["Adventure", "Zelda"]


def test_resolve_console_name_exact_match():
    assert (
        resolve_console_name("Sony PlayStation 2 (PS2)") == "Sony PlayStation 2 (PS2)"
    )


def test_resolve_console_name_fuzzy_match():
    assert resolve_console_name("PS2") == "Sony PlayStation 2 (PS2)"
