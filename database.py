"""
Read The Plaque — database helpers.

Provides get_db() and init_db(). get_db() uses the active Flask application's
DATABASE setting when an app context exists, and DB_PATH otherwise.
"""

import sqlite3

from flask import current_app, has_app_context

from config import DB_PATH


class _ManagedConnection:
    """Wrap sqlite3.Connection so it commits/rolls back and closes on exit."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def __enter__(self) -> sqlite3.Connection:
        return self._conn

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            if exc_type is None:
                self._conn.commit()
            else:
                self._conn.rollback()
        finally:
            self._conn.close()
        return False

    def close(self):
        self._conn.close()

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()


def get_db() -> _ManagedConnection:
    """Open and return a managed SQLite database connection."""
    db_path = (
        current_app.config.get("DATABASE", DB_PATH)
        if has_app_context()
        else DB_PATH
    )
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # better concurrency
    conn.execute("PRAGMA foreign_keys=ON")
    return _ManagedConnection(conn)


def init_db() -> None:
    """Create schema tables if they don't exist, then seed with sample data."""
    with get_db() as db:
        # DDL — executescript issues an implicit COMMIT before running
        db.executescript(
            """
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
            CREATE INDEX IF NOT EXISTS idx_plaques_submitted_by ON plaques(submitted_by);

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

            CREATE INDEX IF NOT EXISTS idx_plaque_images_plaque      ON plaque_images(plaque_id);
            CREATE INDEX IF NOT EXISTS idx_plaque_images_hash        ON plaque_images(image_hash);
            CREATE INDEX IF NOT EXISTS idx_plaque_images_plauqe_hash ON plaque_images(plaque_id, image_hash);

            CREATE INDEX IF NOT EXISTS idx_plaques_approved_created ON plaques(approved, created_at DESC);
            """
        )
