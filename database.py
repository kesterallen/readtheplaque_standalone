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

#    # Seed with sample data if the table is empty
#    count = db.execute("SELECT COUNT(*) FROM plaques").fetchone()[0]
#    if count == 0:
#        with db:
#            _seed(db)
#
#    db.close()
#
#
## ── Seed data ──────────────────────────────────────────────────────────────────
#_SEED_ROWS = [
#    # (slug, title, description, lat, lng, image_file, submitted_by)
#    (
#        "alamo-san-antonio",
#        "The Alamo",
#        "HERE ON THIS SITE IN 1836 THE DEFENDERS OF THE ALAMO MADE THEIR HEROIC STAND FOR TEXAS INDEPENDENCE",
#        29.426,
#        -98.4861,
#        "sample_alamo.jpg",
#        "admin",
#    ),
#    (
#        "liberty-bell-philadelphia",
#        "Liberty Bell",
#        "PROCLAIM LIBERTY THROUGHOUT ALL THE LAND UNTO ALL THE INHABITANTS THEREOF — Leviticus XXV:X",
#        39.9496,
#        -75.1503,
#        "sample_liberty.jpg",
#        "admin",
#    ),
#    (
#        "golden-gate-dedication",
#        "Golden Gate Bridge",
#        "THIS BRIDGE, A SYMBOL OF HUMAN INGENUITY AND PERSEVERANCE, WAS COMPLETED MAY 27, 1937",
#        37.8199,
#        -122.4783,
#        "sample_goldengate.jpg",
#        "admin",
#    ),
#    (
#        "eiffel-tower-paris",
#        "Eiffel Tower",
#        "CONSTRUITE DE 1887 À 1889 PAR GUSTAVE EIFFEL POUR L'EXPOSITION UNIVERSELLE",
#        48.8584,
#        2.2945,
#        "sample_eiffel.jpg",
#        "admin",
#    ),
#    (
#        "colosseum-rome",
#        "Colosseum",
#        "THE FLAVIAN AMPHITHEATRE, COMPLETED IN 80 AD UNDER EMPEROR TITUS, COULD HOLD UP TO 80,000 SPECTATORS",
#        41.8902,
#        12.4922,
#        "sample_colosseum.jpg",
#        "admin",
#    ),
#    (
#        "great-wall-china",
#        "Great Wall of China",
#        "BUILT AND REBUILT FROM THE 7TH CENTURY BC TO THE 16TH CENTURY AD TO PROTECT CHINA FROM INVASIONS",
#        40.4319,
#        116.5704,
#        "sample_greatwall.jpg",
#        "admin",
#    ),
#    (
#        "taj-mahal-agra",
#        "Taj Mahal",
#        "BUILT BY EMPEROR SHAH JAHAN IN MEMORY OF HIS WIFE MUMTAZ MAHAL, COMPLETED IN 1643",
#        27.1751,
#        78.0421,
#        "sample_taj.jpg",
#        "admin",
#    ),
#    (
#        "machu-picchu-peru",
#        "Machu Picchu",
#        "BUILT IN THE 15TH CENTURY BY THE INCA EMPEROR PACHACUTI, REDISCOVERED BY HIRAM BINGHAM IN 1911",
#        -13.1631,
#        -72.545,
#        "sample_machu.jpg",
#        "admin",
#    ),
#    (
#        "acropolis-athens",
#        "Acropolis of Athens",
#        "SYMBOL OF DEMOCRACY AND THE GOLDEN AGE OF CLASSICAL GREECE, CONSTRUCTION BEGAN UNDER PERICLES IN 447 BC",
#        37.9715,
#        23.7257,
#        "sample_acropolis.jpg",
#        "admin",
#    ),
#    (
#        "parthenon-athens",
#        "The Parthenon",
#        "DEDICATED TO ATHENA PARTHENOS, GODDESS OF WISDOM, COMPLETED IN 432 BC UNDER THE SUPERVISION OF PHIDIAS",
#        37.9714,
#        23.7267,
#        "sample_parthenon.jpg",
#        "admin",
#    ),
#    (
#        "sydney-opera-house",
#        "Sydney Opera House",
#        "DESIGNED BY JØRN UTZON AND OPENED BY QUEEN ELIZABETH II ON OCTOBER 20, 1973",
#        -33.8568,
#        151.2153,
#        "sample_sydney.jpg",
#        "admin",
#    ),
#    (
#        "sagrada-familia-barcelona",
#        "Sagrada Família",
#        "DESIGNED BY ANTONI GAUDÍ, CONSTRUCTION BEGAN IN 1882 AND CONTINUES TO THIS DAY",
#        41.4036,
#        2.1744,
#        "sample_sagrada.jpg",
#        "admin",
#    ),
#]
#
#
#def _seed(db: sqlite3.Connection) -> None:
#    """Insert sample plaques into an empty database."""
#    db.executemany(
#        "INSERT OR IGNORE INTO plaques "
#        "(slug, title, description, latitude, longitude, image_file, submitted_by, approved) "
#        "VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
#        _SEED_ROWS,
#    )
