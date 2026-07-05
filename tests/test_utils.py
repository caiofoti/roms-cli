import zipfile

import py7zr

from src.utils import (
    clean_rom_title,
    extract_7z,
    extract_archive,
    extract_nations,
    extract_zip,
)


def test_clean_rom_title_strips_region_and_revision_tags():
    assert clean_rom_title("Crash Bandicoot (USA) (Rev 1).zip") == "Crash Bandicoot"


def test_clean_rom_title_strips_bracket_tags():
    assert (
        clean_rom_title("[BIOS] Nintendo Game Boy Boot ROM (World).zip")
        == "Nintendo Game Boy Boot ROM"
    )


def test_clean_rom_title_empty_input():
    assert clean_rom_title("") == ""


def test_extract_nations_parses_region_list():
    assert extract_nations("Final Fantasy (Europe, USA)") == ["Europe", "USA"]


def test_extract_nations_ignores_unknown_words():
    assert extract_nations("Some Game (Not A Region)") == []


def test_extract_zip_rejects_path_traversal(tmp_path):
    # zip-slip: entrada tenta escrever fora da pasta de destino.
    zip_path = tmp_path / "evil.zip"
    extract_to = tmp_path / "extracted"
    extract_to.mkdir()
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("../../evil.txt", "pwned")

    ok = extract_zip(str(zip_path), str(extract_to))

    assert ok is False
    assert not (tmp_path / "evil.txt").exists()


def test_extract_zip_extracts_and_deletes_archive(tmp_path):
    zip_path = tmp_path / "game.zip"
    extract_to = tmp_path / "extracted"
    extract_to.mkdir()
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("game.gb", b"fake rom data")

    ok = extract_zip(str(zip_path), str(extract_to))

    assert ok is True
    assert not zip_path.exists()
    assert (extract_to / "game.gb").read_bytes() == b"fake rom data"


def test_extract_7z_extracts_and_deletes_archive(tmp_path):
    src_file = tmp_path / "rom.gb"
    src_file.write_bytes(b"fake rom data")
    archive_path = tmp_path / "game.7z"
    with py7zr.SevenZipFile(str(archive_path), "w") as z:
        z.write(str(src_file), "rom.gb")
    src_file.unlink()

    extract_to = tmp_path / "extracted"
    extract_to.mkdir()

    ok = extract_7z(str(archive_path), str(extract_to))

    assert ok is True
    assert not archive_path.exists()
    assert (extract_to / "rom.gb").read_bytes() == b"fake rom data"


def test_extract_7z_rejects_path_traversal(tmp_path):
    src_file = tmp_path / "evil.txt"
    src_file.write_bytes(b"pwned")
    archive_path = tmp_path / "evil.7z"
    with py7zr.SevenZipFile(str(archive_path), "w") as z:
        z.write(str(src_file), "../../evil.txt")
    src_file.unlink()

    extract_to = tmp_path / "extracted"
    extract_to.mkdir()

    ok = extract_7z(str(archive_path), str(extract_to))

    assert ok is False
    assert not (tmp_path / "evil.txt").exists()


def test_extract_archive_passthrough_for_non_archive_extension(tmp_path):
    # .iso/.chd já rodam direto no emulador — não são arquivos compactados,
    # extract_archive não deve tentar extrair nem falhar.
    iso_path = tmp_path / "game.iso"
    iso_path.write_bytes(b"fake iso data")

    assert extract_archive(str(iso_path), str(tmp_path)) is True
    assert iso_path.exists()
