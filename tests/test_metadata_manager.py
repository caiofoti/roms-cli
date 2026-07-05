from src.metadata_manager import _sanitize_retroarch_thumb_name, sanitize_filename


def test_sanitize_filename_replaces_invalid_chars():
    assert sanitize_filename('Game: Special/Edition?.zip') == "Game_ Special_Edition_.zip"


def test_sanitize_filename_truncates_long_names():
    long_name = "a" * 200 + ".zip"
    result = sanitize_filename(long_name)
    assert len(result) <= 100
    assert result.endswith(".zip")


def test_sanitize_retroarch_thumb_name_replaces_ampersand():
    # Regra oficial do RetroArch: '&' no label vira '_' no nome do arquivo.
    assert _sanitize_retroarch_thumb_name("Kirby & The Amazing Mirror") == "Kirby _ The Amazing Mirror"


def test_sanitize_retroarch_thumb_name_strips_invalid_path_chars():
    assert _sanitize_retroarch_thumb_name('Game: Title?') == "Game Title"
