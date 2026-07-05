import src.config as config
from src.downloader import delete_game


def test_delete_game_matches_by_base_name_ignoring_extension(tmp_path, monkeypatch):
    # O link aponta pro nome original (.zip), mas o arquivo local já foi
    # extraído e tem outra extensão (.gb) — delete precisa casar mesmo assim.
    monkeypatch.setattr(config, "ROMS_ROOT", str(tmp_path))
    gb_dir = tmp_path / "gb"
    gb_dir.mkdir()
    (gb_dir / "Some Game (USA).gb").write_bytes(b"fake rom")

    game = {
        "name": "Some Game (USA)",
        "link": "https://archive.org/download/x/Some%20Game%20%28USA%29.zip",
        "folder": "gb",
        "console": "Game Boy (GB)",
    }

    deleted = delete_game(game)

    assert deleted == ["Some Game (USA).gb"]
    assert not (gb_dir / "Some Game (USA).gb").exists()


def test_delete_game_returns_empty_when_nothing_local(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ROMS_ROOT", str(tmp_path))
    game = {
        "name": "Never Downloaded",
        "link": "https://archive.org/download/x/Never%20Downloaded.zip",
        "folder": "gb",
        "console": "Game Boy (GB)",
    }

    assert delete_game(game) == []


def test_delete_game_removes_extracted_directory(tmp_path, monkeypatch):
    # Alguns .zip extraem pra uma pasta (múltiplos arquivos) em vez de 1 arquivo só.
    monkeypatch.setattr(config, "ROMS_ROOT", str(tmp_path))
    gb_dir = tmp_path / "gb"
    extracted = gb_dir / "Multi File Game"
    extracted.mkdir(parents=True)
    (extracted / "track1.bin").write_bytes(b"data")

    game = {
        "name": "Multi File Game",
        "link": "https://archive.org/download/x/Multi%20File%20Game.zip",
        "folder": "gb",
        "console": "Game Boy (GB)",
    }

    deleted = delete_game(game)

    assert deleted == ["Multi File Game"]
    assert not extracted.exists()
