import src.db as db


def test_save_and_load_catalog_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))

    games = [
        {
            "name": "Crash Bandicoot",
            "link": "https://archive.org/download/redump_ps2/Crash%20Bandicoot.zip",
            "size_bytes": 123456,
            "size_str": "120.56 KiB",
            "folder": "ps2",
            "md5": "abc123",
            "sha1": "def456",
            "archive_downloads": 12994,
            "archive_rating": 4.2,
            "archive_reviews": 10,
        }
    ]

    db.save_catalog("Sony PlayStation 2 (PS2)", games)
    loaded = db.load_catalog("Sony PlayStation 2 (PS2)")

    assert loaded is not None
    assert len(loaded) == 1
    assert loaded[0]["name"] == "Crash Bandicoot"
    assert loaded[0]["archive_downloads"] == 12994
    assert loaded[0]["archive_rating"] == 4.2


def test_load_catalog_returns_none_when_not_cached(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))

    assert db.load_catalog("Console Nunca Cacheado") is None


def test_save_catalog_replaces_previous_entries(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))

    db.save_catalog("GB", [{"name": "Old Game", "link": "url", "folder": "gb"}])
    db.save_catalog("GB", [{"name": "New Game", "link": "url", "folder": "gb"}])

    loaded = db.load_catalog("GB")
    assert len(loaded) == 1
    assert loaded[0]["name"] == "New Game"
