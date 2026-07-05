import os
import sqlite3

from src.config import CACHE_FOLDER

DB_PATH = os.path.join(CACHE_FOLDER, "roms_downloader.db")


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS games (
            console TEXT NOT NULL,
            name TEXT NOT NULL,
            link TEXT NOT NULL,
            size_bytes INTEGER,
            size_str TEXT,
            folder TEXT,
            md5 TEXT,
            sha1 TEXT,
            archive_downloads INTEGER,
            archive_rating REAL,
            archive_reviews INTEGER,
            PRIMARY KEY (console, name)
        )
        """
    )
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(games)")}
    for col, col_type in (
        ("archive_downloads", "INTEGER"),
        ("archive_rating", "REAL"),
        ("archive_reviews", "INTEGER"),
    ):
        if col not in existing_cols:
            conn.execute(f"ALTER TABLE games ADD COLUMN {col} {col_type}")
    return conn


def save_catalog(console_name, games):
    """Substitui o catálogo salvo de um console pelo recém-baixado."""
    conn = _connect()
    try:
        conn.execute("DELETE FROM games WHERE console = ?", (console_name,))
        conn.executemany(
            """INSERT INTO games (console, name, link, size_bytes, size_str, folder, md5, sha1,
                                   archive_downloads, archive_rating, archive_reviews)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (
                    console_name,
                    g["name"],
                    g["link"],
                    g.get("size_bytes"),
                    g.get("size_str"),
                    g.get("folder"),
                    g.get("md5"),
                    g.get("sha1"),
                    g.get("archive_downloads"),
                    g.get("archive_rating"),
                    g.get("archive_reviews"),
                )
                for g in games
            ],
        )
        conn.commit()
    finally:
        conn.close()


def load_catalog(console_name):
    """Retorna a lista de jogos salva, ou None se nunca foi cacheada."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT name, link, size_bytes, size_str, folder, md5, sha1, "
            "archive_downloads, archive_rating, archive_reviews "
            "FROM games WHERE console = ?",
            (console_name,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return None

    return [
        {
            "name": r[0],
            "link": r[1],
            "size_bytes": r[2],
            "size_str": r[3],
            "console": console_name,
            "folder": r[4],
            "md5": r[5],
            "sha1": r[6],
            "archive_downloads": r[7],
            "archive_rating": r[8],
            "archive_reviews": r[9],
        }
        for r in rows
    ]
