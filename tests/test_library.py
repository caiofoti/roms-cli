import src.config as config
from src.library import scan_library


def test_scan_library_counts_files_and_skips_existing_covers(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ROMS_ROOT", str(tmp_path))
    gb_dir = tmp_path / "gb"
    gb_dir.mkdir()
    (gb_dir / "Some Game (USA).gb").write_bytes(b"fake rom")
    (gb_dir / "leftover.partial").write_bytes(b"partial, deve ser ignorado")

    monkeypatch.setattr(
        "src.metadata_manager.covers_exist",
        lambda title, console_name: {"pcsx2": False, "retroarch": True},
    )

    total, saved = scan_library()

    assert total == 1  # .partial não conta
    assert saved == 0  # já tinha capa (retroarch=True), não gastou RAWG
