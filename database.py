"""
Read The Plaque — database helpers.

Provides get_db() and init_db(). No Flask dependency — importable and
testable without an app context.
"""

import sqlite3

from config import DB_PATH


def get_db() -> sqlite3.Connection:
    """Open and return a connection to the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # better concurrency
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Create schema tables if they don't exist, then seed with sample data."""
    db = get_db()

    # DDL — executescript issues an implicit COMMIT before running
    db.executescript("""
    CREATE TABLE IF NOT EXISTS plaques (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        slug         TEXT    UNIQUE NOT NULL,
        title        TEXT    NOT NULL,
        description  TEXT,
        latitude     REAL    NOT NULL,
        longitude    REAL    NOT NULL,
        image_file   TEXT    NOT NULL,
        thumb_file   TEXT,
        submitted_by TEXT,
        approved     INTEGER NOT NULL DEFAULT 0,
        is_featured  INTEGER NOT NULL DEFAULT 0,
        created_at   TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at   TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_plaques_slug     ON plaques(slug);
    CREATE INDEX IF NOT EXISTS idx_plaques_location ON plaques(latitude, longitude);
    CREATE INDEX IF NOT EXISTS idx_plaques_approved ON plaques(approved);

    CREATE TABLE IF NOT EXISTS tags (
        id   INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT    UNIQUE NOT NULL COLLATE NOCASE
    );

    CREATE TABLE IF NOT EXISTS plaque_tags (
        plaque_id INTEGER NOT NULL REFERENCES plaques(id) ON DELETE CASCADE,
        tag_id    INTEGER NOT NULL REFERENCES tags(id)    ON DELETE CASCADE,
        PRIMARY KEY (plaque_id, tag_id)
    );

    CREATE INDEX IF NOT EXISTS idx_plaque_tags_plaque ON plaque_tags(plaque_id);
    CREATE INDEX IF NOT EXISTS idx_plaque_tags_tag    ON plaque_tags(tag_id);

    CREATE TABLE IF NOT EXISTS plaque_images (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        plaque_id  INTEGER NOT NULL REFERENCES plaques(id) ON DELETE CASCADE,
        image_file TEXT    NOT NULL,
        thumb_file TEXT,
        image_hash TEXT,
        is_primary INTEGER NOT NULL DEFAULT 0,
        sort_order INTEGER NOT NULL DEFAULT 0,
        created_at TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_plaque_images_plaque ON plaque_images(plaque_id);
    CREATE INDEX IF NOT EXISTS idx_plaque_images_hash   ON plaque_images(plaque_id, image_hash);
    """)

