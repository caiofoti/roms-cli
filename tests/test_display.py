from src.display import _archive_stats_cols


def test_archive_stats_uses_per_game_rawg_rating_when_present():
    # /top popula rating_100 (RAWG, por jogo, escala 0-100) — tem que
    # aparecer em vez da nota genérica do acervo (senão todo jogo do mesmo
    # console mostra a mesma nota, que é o bug que isso corrige).
    game = {"archive_downloads": 211800, "archive_rating": 4.3, "rating_100": 90}
    downloads, rating = _archive_stats_cols(game)
    assert rating == "4.5"  # 90/20


def test_archive_stats_falls_back_to_archive_rating_without_rawg():
    game = {"archive_downloads": 211800, "archive_rating": 4.3}
    downloads, rating = _archive_stats_cols(game)
    assert rating == "4.3"


def test_archive_stats_dash_when_nothing_available():
    game = {"archive_downloads": None, "archive_rating": None}
    downloads, rating = _archive_stats_cols(game)
    assert downloads == "-"
    assert rating == "-"
