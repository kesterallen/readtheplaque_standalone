# display HTML-ifiied text in "description" properly
# TODO: approved/pending/deleted? not just a toggle?
# TODO: move admin password and secret key to env vars
"""
PlaqueWorld - A 3-tier web application for sharing historical plaques.
Tier 1: HTML/CSS/JS frontend (templates + static)
Tier 2: Flask application server (this file)
Tier 3: SQLite database (plaques.db)
"""

import bleach
import hashlib
import io
import math
import os
import re
import uuid
import sqlite3
import urllib.request
import urllib.error
from datetime import datetime
from typing import Optional
from PIL import Image, ImageOps
from flask import (
    Flask, render_template, request, jsonify,
    redirect, url_for, send_from_directory, abort, session
)

# ── Configuration ─────────────────────────────────────────────────────────────
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
# On Fly.io (and similar) a persistent volume is mounted at /data.
# Store the DB and uploads there so they survive redeploys.
_DATA_DIR   = "/data" if os.path.isdir("/data") else BASE_DIR
DB_PATH     = os.path.join(_DATA_DIR, "plaques.db")
UPLOAD_DIR  = os.path.join(_DATA_DIR, "uploads")
THUMB_DIR   = os.path.join(_DATA_DIR, "thumbs")
THUMB_SIZE  = (400, 300)
ALLOWED_EXT = {"png", "jpg", "jpeg", "gif", "webp"}
MAX_MB      = 16

# TODO Change this in production!
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "plaqueadmin")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")
app.config["MAX_CONTENT_LENGTH"] = MAX_MB * 1024 * 1024
app.config["UPLOAD_FOLDER"]      = UPLOAD_DIR

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(THUMB_DIR,  exist_ok=True)


def subdir_path(base_dir: str, filename: str) -> str:
    """Return full path using first 2 hex chars as a subdirectory bucket.

    e.g. "abcdef12.jpg" -> "<base_dir>/ab/abcdef12.jpg"
    Falls back to base_dir directly for legacy flat filenames (seed data).
    """
    if len(filename) >= 2 and all(c in "0123456789abcdef" for c in filename[:2]):
        bucket = filename[:2]
        directory = os.path.join(base_dir, bucket)
        os.makedirs(directory, exist_ok=True)
        return os.path.join(directory, filename)
    return os.path.join(base_dir, filename)


def new_image_filename(ext: str) -> str:
    """Generate a UUID-based filename and its subdirectory path."""
    return f"{uuid.uuid4().hex}.{ext}"


def new_thumb_filename() -> str:
    return f"{uuid.uuid4().hex}_thumb.jpg"

# ── Thumbnail helper ───────────────────────────────────────────────────────────
def _save_thumbnail(img: Image.Image, thumb_filename: str) -> Optional[str]:
    """Cover-crop img to THUMB_SIZE and save as JPEG. Returns filename or None."""
    try:
        ImageOps.fit(img.convert("RGB"), THUMB_SIZE, Image.LANCZOS).save(
            subdir_path(THUMB_DIR, thumb_filename), "JPEG", quality=82, optimize=True
        )
        return thumb_filename
    except Exception:
        return None

def make_thumbnail(image_filename: str, thumb_filename: str) -> Optional[str]:
    """Create thumbnail from a saved upload file. image_filename is relative."""
    try:
        with Image.open(subdir_path(UPLOAD_DIR, image_filename)) as img:
            return _save_thumbnail(img, thumb_filename)
    except Exception:
        return None

def make_thumbnail_from_bytes(img_bytes: bytes, thumb_filename: str) -> Optional[str]:
    try:
        with Image.open(io.BytesIO(img_bytes)) as img:
            return _save_thumbnail(img, thumb_filename)
    except Exception:
        return None


# ── Database helpers ───────────────────────────────────────────────────────────
def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # better concurrency
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    db = get_db()
    # DDL — executescript issues an implicit COMMIT before running, safe for schema work
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
        created_at   TEXT    NOT NULL
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
        created_at TEXT    NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_plaque_images_plaque ON plaque_images(plaque_id);
    CREATE INDEX IF NOT EXISTS idx_plaque_images_hash   ON plaque_images(plaque_id, image_hash);
    """)

#    # Seed with sample data if empty — wrap in transaction so it's all-or-nothing
#    count = db.execute("SELECT COUNT(*) FROM plaques").fetchone()[0]
#    if count == 0:
#        with db:
#            seed_data = [
#                ('alamo-san-antonio', 'The Alamo',
#                 'HERE ON THIS SITE IN 1836 THE DEFENDERS OF THE ALAMO MADE THEIR HEROIC STAND FOR TEXAS INDEPENDENCE',
#                 29.426, -98.4861, 'sample_alamo.jpg', 'admin'),
#                ('liberty-bell-philadelphia', 'Liberty Bell',
#                 'PROCLAIM LIBERTY THROUGHOUT ALL THE LAND UNTO ALL THE INHABITANTS THEREOF — Leviticus XXV:X',
#                 39.9496, -75.1503, 'sample_liberty.jpg', 'admin'),
#                ('golden-gate-dedication', 'Golden Gate Bridge',
#                 'THIS BRIDGE, A SYMBOL OF HUMAN INGENUITY AND PERSEVERANCE, WAS COMPLETED MAY 27, 1937',
#                 37.8199, -122.4783, 'sample_goldengate.jpg', 'admin'),
#                ('ellis-island-memorial', 'Ellis Island',
#                 'THROUGH THESE DOORS PASSED MORE THAN 12 MILLION IMMIGRANTS IN SEARCH OF FREEDOM AND A NEW LIFE',
#                 40.6995, -74.0397, 'sample_ellis.jpg', 'admin'),
#                ('lincoln-memorial-dc', 'Lincoln Memorial',
#                 'IN THIS TEMPLE, AS IN THE HEARTS OF THE PEOPLE FOR WHOM HE SAVED THE UNION, THE MEMORY OF ABRAHAM LINCOLN IS ENSHRINED FOREVER',
#                 38.8893, -77.0502, 'sample_lincoln.jpg', 'admin'),
#                ('space-needle-seattle', 'Space Needle',
#                 "BUILT FOR THE 1962 WORLD'S FAIR, THIS STRUCTURE STANDS AS A SYMBOL OF SEATTLE'S SPIRIT AND INNOVATION",
#                 47.6205, -122.3493, 'sample_needle.jpg', 'admin'),
#                ('eiffel-tower-paris', 'Eiffel Tower',
#                 "CONSTRUITE DE 1887 À 1889 PAR GUSTAVE EIFFEL POUR L'EXPOSITION UNIVERSELLE",
#                 48.8584, 2.2945, 'sample_eiffel.jpg', 'admin'),
#                ('big-ben-london', 'Big Ben',
#                 "THE CLOCK TOWER OF THE PALACE OF WESTMINSTER, RENAMED ELIZABETH TOWER IN 2012 TO MARK THE QUEEN'S DIAMOND JUBILEE",
#                 51.5007, -0.1246, 'sample_bigben.jpg', 'admin'),
#                ('colosseum-rome', 'Colosseum',
#                 'THE FLAVIAN AMPHITHEATRE, COMPLETED IN 80 AD UNDER EMPEROR TITUS, COULD HOLD UP TO 80,000 SPECTATORS',
#                 41.8902, 12.4922, 'sample_colosseum.jpg', 'admin'),
#                ('great-wall-china', 'Great Wall of China',
#                 'BUILT AND REBUILT FROM THE 7TH CENTURY BC TO THE 16TH CENTURY AD TO PROTECT CHINA FROM INVASIONS',
#                 40.4319, 116.5704, 'sample_greatwall.jpg', 'admin'),
#                ('sydney-opera-house', 'Sydney Opera House',
#                 'DESIGNED BY JØRN UTZON AND OPENED BY QUEEN ELIZABETH II ON OCTOBER 20, 1973',
#                 -33.8568, 151.2153, 'sample_sydney.jpg', 'admin'),
#                ('machu-picchu-peru', 'Machu Picchu',
#                 'BUILT IN THE 15TH CENTURY BY THE INCA EMPEROR PACHACUTI, REDISCOVERED BY HIRAM BINGHAM IN 1911',
#                 -13.1631, -72.545, 'sample_machu.jpg', 'admin'),
#                ('taj-mahal-agra', 'Taj Mahal',
#                 'BUILT BY EMPEROR SHAH JAHAN IN MEMORY OF HIS WIFE MUMTAZ MAHAL, COMPLETED IN 1643',
#                 27.1751, 78.0421, 'sample_taj.jpg', 'admin'),
#                ('statue-of-liberty', 'Statue of Liberty',
#                 'GIVE ME YOUR TIRED, YOUR POOR, YOUR HUDDLED MASSES YEARNING TO BREATHE FREE',
#                 40.6892, -74.0445, 'sample_liberty2.jpg', 'admin'),
#                ('mount-rushmore', 'Mount Rushmore',
#                 'DEDICATED 1941 — COMMEMORATING THE BIRTH, GROWTH, AND PRESERVATION OF THIS NATION',
#                 43.8791, -103.4591, 'sample_rushmore.jpg', 'admin'),
#                ('acropolis-athens', 'Acropolis of Athens',
#                 'SYMBOL OF DEMOCRACY AND THE GOLDEN AGE OF CLASSICAL GREECE, CONSTRUCTION BEGAN UNDER PERICLES IN 447 BC',
#                 37.9715, 23.7257, 'sample_acropolis.jpg', 'admin'),
#                ('angkor-wat-cambodia', 'Angkor Wat',
#                 'CONSTRUCTED IN THE EARLY 12TH CENTURY BY SURYAVARMAN II, THE LARGEST RELIGIOUS MONUMENT IN THE WORLD',
#                 13.4125, 103.867, 'sample_angkor.jpg', 'admin'),
#                ('christ-redeemer-rio', 'Christ the Redeemer',
#                 'INAUGURATED ON OCTOBER 12, 1931, THIS ART DECO STATUE STANDS 30 METRES TALL ATOP CORCOVADO MOUNTAIN',
#                 -22.9519, -43.2105, 'sample_christ.jpg', 'admin'),
#                ('petra-jordan', 'Petra',
#                 'THE ROSE-RED CITY HALF AS OLD AS TIME — CARVED INTO ROCK BY THE NABATAEAN KINGDOM FROM THE 4TH CENTURY BC',
#                 30.3285, 35.4444, 'sample_petra.jpg', 'admin'),
#                ('chichen-itza-mexico', 'Chichén Itzá',
#                 'EL CASTILLO WAS BUILT BY THE MAYA CIVILIZATION AS A TEMPLE TO KUKULCAN, CIRCA 800–900 AD',
#                 20.6843, -88.5678, 'sample_chichen.jpg', 'admin'),
#                ('stonehenge-england', 'Stonehenge',
#                 "ERECTED BETWEEN 3000 AND 1500 BC, ITS PURPOSE REMAINS ONE OF HISTORY'S GREAT MYSTERIES",
#                 51.1789, -1.8262, 'sample_stonehenge.jpg', 'admin'),
#                ('parthenon-athens', 'The Parthenon',
#                 'DEDICATED TO ATHENA PARTHENOS, GODDESS OF WISDOM, COMPLETED IN 432 BC UNDER THE SUPERVISION OF PHIDIAS',
#                 37.9714, 23.7267, 'sample_parthenon.jpg', 'admin'),
#                ('versailles-palace', 'Palace of Versailles',
#                 'TRANSFORMED BY LOUIS XIV INTO THE MOST SPLENDID ROYAL RESIDENCE IN EUROPE, SEAT OF FRENCH GOVERNMENT 1682–1789',
#                 48.8049, 2.1204, 'sample_versailles.jpg', 'admin'),
#                ('alhambra-granada', 'The Alhambra',
#                 'BUILT PRIMARILY IN THE 13TH AND 14TH CENTURIES, A MASTERPIECE OF MOORISH ARCHITECTURE AND ISLAMIC ART',
#                 37.176, -3.5881, 'sample_alhambra.jpg', 'admin'),
#                ('sagrada-familia-barcelona', 'Sagrada Família',
#                 'DESIGNED BY ANTONI GAUDÍ, CONSTRUCTION BEGAN IN 1882 AND CONTINUES TO THIS DAY — A TESTAMENT TO HUMAN DEVOTION',
#                 41.4036, 2.1744, 'sample_sagrada.jpg', 'admin'),
#                ('tower-of-london', 'Tower of London',
#                 'FOUNDED IN 1066 BY WILLIAM THE CONQUEROR, SERVING AS ROYAL PALACE, FORTRESS, PRISON, AND TREASURY',
#                 51.5081, -0.0759, 'sample_tower.jpg', 'admin'),
#                ('forbidden-city-beijing', 'The Forbidden City',
#                 'BUILT BETWEEN 1406 AND 1420, SERVED AS THE HOME OF 24 EMPERORS OF THE MING AND QING DYNASTIES',
#                 39.9163, 116.3972, 'sample_forbidden.jpg', 'admin'),
#                ('notre-dame-paris', 'Notre-Dame de Paris',
#                 'CONSTRUCTION BEGAN IN 1163 UNDER BISHOP MAURICE DE SULLY. ONE OF THE FINEST EXAMPLES OF FRENCH GOTHIC ARCHITECTURE',
#                 48.853, 2.3499, 'sample_notredame.jpg', 'admin'),
#                ('hagia-sophia-istanbul', 'Hagia Sophia',
#                 'COMPLETED IN 537 AD UNDER EMPEROR JUSTINIAN I. CATHEDRAL, MOSQUE, AND NOW MUSEUM — WITNESS TO 1500 YEARS OF HISTORY',
#                 41.0086, 28.9802, 'sample_hagia.jpg', 'admin'),
#                ('st-peters-vatican', "St. Peter's Basilica",
#                 'THE LARGEST CHURCH IN THE WORLD, BUILT OVER THE TOMB OF SAINT PETER. MICHELANGELO DESIGNED ITS ICONIC DOME IN 1547',
#                 41.9022, 12.4539, 'sample_stpeters.jpg', 'admin'),
#                ('westminster-abbey', 'Westminster Abbey',
#                 'FOUNDED IN 960 AD, SITE OF ROYAL CORONATIONS SINCE 1066 AND RESTING PLACE OF MONARCHS, POETS, AND SCIENTISTS',
#                 51.4994, -0.1273, 'sample_westminster.jpg', 'admin'),
#                ('mont-saint-michel', 'Mont Saint-Michel',
#                 'THE ABBEY WAS FOUNDED IN 708 AD BY BISHOP AUBERT OF AVRANCHES FOLLOWING A VISION OF THE ARCHANGEL MICHAEL',
#                 48.6361, -1.5115, 'sample_montmichel.jpg', 'admin'),
#                ('kremlin-moscow', 'The Moscow Kremlin',
#                 'THE ORIGINAL WOODEN KREMLIN WAS BUILT IN 1156. THE PRESENT WALLS DATE FROM 1485–1495 UNDER IVAN THE GREAT',
#                 55.752, 37.6175, 'sample_kremlin.jpg', 'admin'),
#                ('empire-state-building', 'Empire State Building',
#                 "OPENED MAY 1, 1931. BUILT IN JUST 410 DAYS, IT STOOD AS THE WORLD'S TALLEST BUILDING FOR 40 YEARS",
#                 40.7484, -73.9857, 'sample_empire.jpg', 'admin'),
#                ('burj-khalifa-dubai', 'Burj Khalifa',
#                 'OPENED JANUARY 4, 2010. AT 828 METRES, THE TALLEST STRUCTURE EVER BUILT BY HUMAN HANDS',
#                 25.1972, 55.2744, 'sample_burj.jpg', 'admin'),
#                ('hoover-dam', 'Hoover Dam',
#                 'DEDICATED SEPTEMBER 30, 1935 BY PRESIDENT FRANKLIN D. ROOSEVELT. BUILT BY 21,000 WORKERS IN THE HEART OF THE MOJAVE',
#                 36.016, -114.7377, 'sample_hoover.jpg', 'admin')
#
#            ]
#            now = datetime.utcnow().isoformat()
#            for i in range(1000):
#                db.executemany(
#                    "INSERT OR IGNORE INTO plaques "
#                    "(slug,title,description,latitude,longitude,"
#                    "image_file,submitted_by,approved,created_at)"
#                    " VALUES (?,?,?,?,?,?,?,1,?)",
#                    [(row[0]+f" {i}", *row[1:], now) for row in seed_data]
#                )
#    db.close()


def plaque_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    img = d["image_file"]
    d["image_url"] = f"/uploads/{img[:2]}/{img}" if (
        len(img) >= 2 and all(c in "0123456789abcdef" for c in img[:2])
    ) else f"/uploads/{img}"
    thumb = d.get("thumb_file")
    if thumb:
        d["thumb_url"] = f"/thumbs/{thumb[:2]}/{thumb}" if (
            len(thumb) >= 2 and all(c in "0123456789abcdef" for c in thumb[:2])
        ) else f"/thumbs/{thumb}"
    else:
        d["thumb_url"] = d["image_url"]
    return d


# ── Image helpers ──────────────────────────────────────────────────────────────
def get_images_for_plaque(db: sqlite3.Connection, plaque_id: int) -> list[dict]:
    """Return list of image dicts for a plaque, primary first."""
    rows = db.execute(
        "SELECT * FROM plaque_images WHERE plaque_id=? ORDER BY is_primary DESC, sort_order ASC, id ASC",
        (plaque_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def image_url(filename: str) -> str:
    return f"/uploads/{filename[:2]}/{filename}" if (
        len(filename) >= 2 and all(c in "0123456789abcdef" for c in filename[:2])
    ) else f"/uploads/{filename}"


def thumb_url(filename: Optional[str]) -> Optional[str]:
    if not filename:
        return None
    return f"/thumbs/{filename[:2]}/{filename}" if (
        len(filename) >= 2 and all(c in "0123456789abcdef" for c in filename[:2])
    ) else f"/thumbs/{filename}"


def add_image_to_plaque(
    db: sqlite3.Connection,
    plaque_id: int,
    file_obj: io.IOBase,
    ext: str,
    is_primary: bool = False,
    sort_order: int = 0,
) -> dict:
    """Save a file, create thumbnail, insert into plaque_images.

    Returns a dict with keys: image_file, thumb_file, duplicate (bool).
    If the image hash already exists for this plaque, no file is saved and
    duplicate=True is returned so callers can inform the user.
    """
    data = file_obj.read()
    image_hash = hashlib.sha256(data).hexdigest()

    # Reject if this exact image already exists for this plaque
    existing = db.execute(
        "SELECT id FROM plaque_images WHERE plaque_id=? AND image_hash=?",
        (plaque_id, image_hash),
    ).fetchone()
    if existing:
        return {"image_file": None, "thumb_file": None, "duplicate": True}

    filename = new_image_filename(ext)
    with open(subdir_path(UPLOAD_DIR, filename), "wb") as fh:
        fh.write(data)
    thumb_filename = new_thumb_filename()
    thumb_ok = make_thumbnail(filename, thumb_filename)
    now = datetime.utcnow().isoformat()
    db.execute(
        "INSERT INTO plaque_images"
        " (plaque_id, image_file, thumb_file, image_hash, is_primary, sort_order, created_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (plaque_id, filename, thumb_filename if thumb_ok else None,
         image_hash, 1 if is_primary else 0, sort_order, now),
    )
    # Keep plaques.image_file / thumb_file in sync with primary image
    if is_primary:
        db.execute(
            "UPDATE plaques SET image_file=?, thumb_file=? WHERE id=?",
            (filename, thumb_filename if thumb_ok else None, plaque_id),
        )
    return {"image_file": filename, "thumb_file": thumb_filename if thumb_ok else None, "duplicate": False}


def sync_primary_image(db: sqlite3.Connection, plaque_id: int) -> None:
    """Update plaques.image_file to match the current primary image in plaque_images."""
    primary = db.execute(
        "SELECT image_file, thumb_file FROM plaque_images WHERE plaque_id=? AND is_primary=1 LIMIT 1",
        (plaque_id,),
    ).fetchone()
    if not primary:
        # Fall back to first image
        primary = db.execute(
            "SELECT image_file, thumb_file FROM plaque_images WHERE plaque_id=? ORDER BY sort_order, id LIMIT 1",
            (plaque_id,),
        ).fetchone()
    if primary:
        db.execute(
            "UPDATE plaques SET image_file=?, thumb_file=? WHERE id=?",
            (primary["image_file"], primary["thumb_file"], plaque_id),
        )


# ── Tag helpers ────────────────────────────────────────────────────────────────
def get_tags_for_plaque(db: sqlite3.Connection, plaque_id: int) -> list[str]:
    """Return list of tag name strings for a plaque."""
    rows = db.execute(
        "SELECT t.name FROM tags t "
        "JOIN plaque_tags pt ON pt.tag_id = t.id "
        "WHERE pt.plaque_id = ? ORDER BY t.name",
        (plaque_id,),
    ).fetchall()
    return [r["name"] for r in rows]


def set_tags_for_plaque(db: sqlite3.Connection, plaque_id: int, tag_names: list[str]) -> None:
    """Replace all tags for a plaque with the given list of tag name strings."""
    db.execute("DELETE FROM plaque_tags WHERE plaque_id=?", (plaque_id,))
    for name in tag_names:
        name = name.strip().lower()
        if not name:
            continue
        db.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (name,))
        tag_id = db.execute("SELECT id FROM tags WHERE name=?", (name,)).fetchone()["id"]
        db.execute(
            "INSERT OR IGNORE INTO plaque_tags (plaque_id, tag_id) VALUES (?,?)",
            (plaque_id, tag_id),
        )


def parse_tags(raw: str) -> list[str]:
    """Parse a comma-separated tag string into a cleaned list."""
    return [t.strip().lower() for t in raw.split(",") if t.strip()]


# ── HTML sanitisation ─────────────────────────────────────────────────────────
# Tags and attributes that are safe to render from user input
_ALLOWED_TAGS: list[str] = [
    "b", "i", "em", "strong", "u", "s", "del",
    "p", "br",
    "ul", "ol", "li",
    "blockquote",
    "h3", "h4", "h5", "h6",
    "a",
    "pre", "code",
]
_ALLOWED_ATTRS: dict[str, list[str]] = {
    "a": ["href", "title"],
}


def sanitise_description(raw: str) -> str:
    """Strip unsafe HTML from user-supplied description text.

    Allows a limited set of formatting tags so submitters can use basic
    markup (bold, lists, links) while preventing XSS (script injection,
    event handlers, dangerous hrefs, etc.).
    Returns an HTML-safe string ready to render with |safe in templates.
    """
    return bleach.clean(
        raw,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRS,
        strip=True,          # remove disallowed tags entirely rather than escaping them
        strip_comments=True,
    )


# ── Admin helpers ──────────────────────────────────────────────────────────────
def is_admin() -> bool:
    return session.get("admin") is True


# ── Routes ─────────────────────────────────────────────────────────────────────
@app.route("/")
@app.route("/page/<int:page>")
def index(page=1):
    per_page = 12
    page     = max(1, page)
    offset   = (page - 1) * per_page

    with get_db() as db:
        total = db.execute("SELECT COUNT(*) FROM plaques WHERE approved=1").fetchone()[0]

        # Featured plaque: explicit is_featured flag, else fall back to most recent
        featured_row = db.execute(
            "SELECT * FROM plaques WHERE approved=1 AND is_featured=1 LIMIT 1"
        ).fetchone()
        if not featured_row:
            featured_row = db.execute(
                "SELECT * FROM plaques WHERE approved=1 ORDER BY created_at DESC LIMIT 1"
            ).fetchone()

        featured_id = featured_row["id"] if featured_row else None

        # Recent grid: exclude the featured plaque so it doesn't appear twice
        rows = db.execute(
            "SELECT * FROM plaques WHERE approved=1 AND id != ? "
            "ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (featured_id or -1, per_page, offset),
        ).fetchall()

    featured = plaque_to_dict(featured_row) if (page == 1 and featured_row) else None
    recent   = [plaque_to_dict(r) for r in rows]

    total_pages = max(1, -(-total // per_page))   # ceiling division
    return render_template("index.html",
                           featured=featured, recent=recent,
                           total=total, page=page, total_pages=total_pages)


@app.route("/map")
@app.route("/map/<path:coords>")
def map_view(coords=None):
    lat, lng, zoom = 20.0, 10.0, 2
    if coords:
        parts = coords.split("/")
        if len(parts) == 3:
            try:
                lat  = max(-90.0,  min(90.0,  float(parts[0])))
                lng  = max(-180.0, min(180.0, float(parts[1])))
                zoom = max(1,      min(19,    int(parts[2])))
            except ValueError:
                pass  # bad values → fall back to defaults
    with get_db() as db:
        total = db.execute("SELECT COUNT(*) FROM plaques WHERE approved=1").fetchone()[0]
    return render_template("map.html", total=total, init_lat=lat, init_lng=lng, init_zoom=zoom)


@app.route("/submit", methods=["GET", "POST"])
def submit():
    if request.method == "GET":
        return render_template("submit.html")

    errors = []
    title        = request.form.get("title", "").strip()
    description  = request.form.get("description", "").strip()
    submitted_by = request.form.get("submitted_by", "anonymous").strip() or "anonymous"

    try:
        lat = float(request.form.get("latitude", ""))
        lng = float(request.form.get("longitude", ""))
    except ValueError:
        errors.append("Valid latitude and longitude are required.")
        lat = lng = 0.0

    if not title:
        errors.append("Title is required.")
    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        errors.append("Coordinates out of range.")

    image_files = request.files.getlist("images")
    image_files = [f for f in image_files if f and f.filename]
    if not image_files:
        errors.append("At least one image is required.")
    else:
        for f in image_files:
            ext = f.filename.rsplit(".", 1)[-1].lower()
            if ext not in ALLOWED_EXT:
                errors.append(f"'{f.filename}': allowed types are {', '.join(ALLOWED_EXT)}")

    if errors:
        return jsonify({"ok": False, "errors": errors}), 400

    base_slug = "-".join(title.lower().split())[:60]
    slug = f"{base_slug}-{uuid.uuid4().hex[:6]}"
    raw_tags = request.form.get("tags", "")
    tag_names = parse_tags(raw_tags)

    with get_db() as db:
        duplicates = []
        saved_images = []

        # Save all images first so we have a real primary filename before inserting the plaque
        for i, f in enumerate(image_files):
            ext = f.filename.rsplit(".", 1)[-1].lower()
            # We don't have a plaque_id yet; write file and get hash, insert row after plaque created
            data = f.read()
            image_hash = __import__("hashlib").sha256(data).hexdigest()
            filename = new_image_filename(ext)
            with open(subdir_path(UPLOAD_DIR, filename), "wb") as fh:
                fh.write(data)
            thumb_filename = new_thumb_filename()
            thumb_ok = make_thumbnail(filename, thumb_filename)
            saved_images.append({
                "filename": filename,
                "thumb": thumb_filename if thumb_ok else None,
                "hash": image_hash,
                "original_name": f.filename,
            })

        if not saved_images:
            return jsonify({"ok": False, "errors": ["No images could be saved."]}), 400

        primary = saved_images[0]
        db.execute(
            "INSERT INTO plaques "
            "(slug,title,description,latitude,longitude,"
            "image_file,thumb_file,submitted_by,approved,created_at)"
            " VALUES (?,?,?,?,?,?,?,?,0,?)",
            (slug, title, description, lat, lng,
             primary["filename"], primary["thumb"],
             submitted_by, datetime.utcnow().isoformat())
        )
        plaque_id = db.execute("SELECT id FROM plaques WHERE slug=?", (slug,)).fetchone()["id"]

        # Insert plaque_images rows, deduplicating by hash within this plaque
        seen_hashes = set()
        saved = 0
        for i, img in enumerate(saved_images):
            if img["hash"] in seen_hashes:
                duplicates.append(img["original_name"])
                # Clean up the already-written duplicate file
                try:
                    os.remove(subdir_path(UPLOAD_DIR, img["filename"]))
                    if img["thumb"]: os.remove(subdir_path(THUMB_DIR, img["thumb"]))
                except OSError:
                    pass
                continue
            seen_hashes.add(img["hash"])
            db.execute(
                "INSERT INTO plaque_images"
                " (plaque_id, image_file, thumb_file, image_hash, is_primary, sort_order, created_at)"
                " VALUES (?,?,?,?,?,?,?)",
                (plaque_id, img["filename"], img["thumb"], img["hash"],
                 1 if saved == 0 else 0, i, datetime.utcnow().isoformat())
            )
            saved += 1

        set_tags_for_plaque(db, plaque_id, tag_names)

    resp = {"ok": True, "slug": slug, "pending": True}
    if duplicates:
        resp["duplicates"] = duplicates
    return jsonify(resp)


@app.route("/plaque/<slug>")
def plaque_detail(slug):
    with get_db() as db:
        row = db.execute(
            "SELECT * FROM plaques WHERE slug=? AND approved=1", (slug,)
        ).fetchone()
        if not row:
            abort(404)
        tags   = get_tags_for_plaque(db, row["id"])
        images = get_images_for_plaque(db, row["id"])
    plaque = plaque_to_dict(row)
    plaque["tags"] = tags
    plaque["images"] = [
        {"image_url": image_url(img["image_file"]),
         "thumb_url": thumb_url(img["thumb_file"]) or image_url(img["image_file"]),
         "id": img["id"], "is_primary": img["is_primary"]}
        for img in images
    ]
    if plaque.get("description"):
        plaque["description_html"] = sanitise_description(plaque["description"])
    else:
        plaque["description_html"] = ""
    return render_template("detail.html", plaque=plaque)


@app.route("/tag/<tag_name>")
def tag_page(tag_name):
    tag_name = tag_name.strip().lower()
    with get_db() as db:
        tag = db.execute("SELECT * FROM tags WHERE name=?", (tag_name,)).fetchone()
        if not tag:
            abort(404)
        rows = db.execute(
            "SELECT p.* FROM plaques p "
            "JOIN plaque_tags pt ON pt.plaque_id = p.id "
            "JOIN tags t ON t.id = pt.tag_id "
            "WHERE t.name=? AND p.approved=1 ORDER BY p.created_at DESC",
            (tag_name,),
        ).fetchall()
    plaques = [plaque_to_dict(r) for r in rows]
    return render_template("tag.html", tag=tag_name, plaques=plaques)


# ── Admin ──────────────────────────────────────────────────────────────────────
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(url_for("admin_queue"))
        error = "Incorrect password."
    return render_template("admin_login.html", error=error)


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/admin/queue")
def admin_queue():
    if not is_admin():
        return redirect(url_for("admin_login"))
    with get_db() as db:
        pending = db.execute(
            "SELECT * FROM plaques WHERE approved=0 ORDER BY created_at ASC"
        ).fetchall()
    return render_template("admin_queue.html", pending=[plaque_to_dict(p) for p in pending])


@app.route("/admin/plaques")
def admin_plaques():
    if not is_admin():
        return redirect(url_for("admin_login"))
    page     = max(1, request.args.get("page", 1, type=int))
    per_page = 24
    offset   = (page - 1) * per_page
    with get_db() as db:
        rows  = db.execute(
            "SELECT * FROM plaques ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (per_page, offset)
        ).fetchall()
        total = db.execute("SELECT COUNT(*) FROM plaques").fetchone()[0]
    total_pages = max(1, -(-total // per_page))
    return render_template("admin_plaques.html",
                           plaques=[plaque_to_dict(r) for r in rows],
                           page=page, total_pages=total_pages, total=total)


# TODO: remove this
@app.route("/admin/approve/all", methods=["GET", "POST"])
def admin_approve_all():
    with get_db() as db:
        db.execute("UPDATE plaques SET approved=1")
    return jsonify({"ok": True})

@app.route("/admin/approve/<int:plaque_id>", methods=["POST"])
def admin_approve(plaque_id):
    if not is_admin():
        return jsonify({"ok": False, "error": "Not authenticated"}), 403
    with get_db() as db:
        db.execute("UPDATE plaques SET approved=1 WHERE id=?", (plaque_id,))
    return jsonify({"ok": True})


@app.route("/admin/reject/<int:plaque_id>", methods=["POST"])
def admin_reject(plaque_id):
    if not is_admin():
        return jsonify({"ok": False, "error": "Not authenticated"}), 403
    with get_db() as db:
        row = db.execute("SELECT image_file, thumb_file FROM plaques WHERE id=?", (plaque_id,)).fetchone()
        if row:
            for col, folder in [("image_file", UPLOAD_DIR), ("thumb_file", THUMB_DIR)]:
                f = row[col]
                if f:
                    try:
                        os.remove(subdir_path(folder, f))
                    except OSError:
                        pass
            db.execute("DELETE FROM plaques WHERE id=?", (plaque_id,))
    return jsonify({"ok": True})


@app.route("/admin/edit/<int:plaque_id>", methods=["GET", "POST"])
def admin_edit(plaque_id):
    if not is_admin():
        return redirect(url_for("admin_login"))

    with get_db() as db:
        row = db.execute("SELECT * FROM plaques WHERE id=?", (plaque_id,)).fetchone()
    if not row:
        abort(404)

    if request.method == "GET":
        with get_db() as db:
            tags   = get_tags_for_plaque(db, plaque_id)
            images = get_images_for_plaque(db, plaque_id)
        plaque = plaque_to_dict(row)
        plaque["tags"] = tags
        plaque["images"] = [
            {"image_url": image_url(img["image_file"]),
             "thumb_url": thumb_url(img["thumb_file"]) or image_url(img["image_file"]),
             "id": img["id"], "is_primary": img["is_primary"], "sort_order": img["sort_order"]}
            for img in images
        ]
        return render_template("admin_edit.html", plaque=plaque)

    # POST — save edits
    errors = []
    title       = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    submitted_by= request.form.get("submitted_by", "").strip()
    approved    = 1 if request.form.get("approved") else 0

    try:
        lat = float(request.form.get("latitude", ""))
        lng = float(request.form.get("longitude", ""))
    except ValueError:
        errors.append("Valid latitude and longitude are required.")
        lat = lng = 0.0

    if not title:
        errors.append("Title is required.")
    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        errors.append("Coordinates out of range.")

    # Optional new image
    new_image   = request.files.get("image")
    new_img_file   = row["image_file"]
    new_thumb_file = row["thumb_file"]

    if new_image and new_image.filename:
        ext = new_image.filename.rsplit(".", 1)[-1].lower()
        if ext not in ALLOWED_EXT:
            errors.append(f"Allowed image types: {', '.join(ALLOWED_EXT)}")
        else:
            # Save new image and thumbnail, delete old ones
            filename = new_image_filename(ext)
            new_image.save(subdir_path(UPLOAD_DIR, filename))
            thumb_filename = new_thumb_filename()
            thumb_ok = make_thumbnail(filename, thumb_filename)

            for old_f, folder in [(row["image_file"], UPLOAD_DIR), (row["thumb_file"], THUMB_DIR)]:
                if old_f:
                    try:
                        os.remove(subdir_path(folder, old_f))
                    except OSError:
                        pass

            new_img_file   = filename
            new_thumb_file = thumb_filename if thumb_ok else None

    if errors:
        return render_template("admin_edit.html", plaque=plaque_to_dict(row), errors=errors)

    set_featured = bool(request.form.get("set_featured"))

    raw_tags = request.form.get("tags", "")
    tag_names = parse_tags(raw_tags)

    with get_db() as db:
        if set_featured:
            db.execute("UPDATE plaques SET is_featured=0")
        db.execute(
            "UPDATE plaques SET title=?, description=?, latitude=?, longitude=?,"
            " submitted_by=?, approved=?, is_featured=?, image_file=?, thumb_file=? WHERE id=?",
            (title, description, lat, lng,
             submitted_by, approved, 1 if set_featured else 0,
             new_img_file, new_thumb_file, plaque_id)
        )
        set_tags_for_plaque(db, plaque_id, tag_names)

    return redirect(url_for("admin_queue"))


@app.route("/admin/rotate/<int:plaque_id>", methods=["POST"])
def admin_rotate(plaque_id):
    """Rotate 90° clockwise. ?type=image treats plaque_id as a plaque_images.id."""
    if not is_admin():
        return jsonify({"ok": False, "error": "Not authenticated"}), 403

    use_image_id = request.args.get("type") == "image"

    with get_db() as db:
        if use_image_id:
            row = db.execute(
                "SELECT image_file, thumb_file FROM plaque_images WHERE id=?", (plaque_id,)
            ).fetchone()
        else:
            row = db.execute(
                "SELECT image_file, thumb_file FROM plaques WHERE id=?", (plaque_id,)
            ).fetchone()
    if not row:
        return jsonify({"ok": False, "error": "Not found"}), 404

    img_path = subdir_path(UPLOAD_DIR, row["image_file"])
    if not os.path.exists(img_path):
        return jsonify({"ok": False, "error": "Image file not found"}), 404

    try:
        with Image.open(img_path) as img:
            img.rotate(-90, expand=True).save(img_path)
        if row["thumb_file"]:
            make_thumbnail(row["image_file"], row["thumb_file"])
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    return jsonify({"ok": True})


@app.route("/admin/feature/<int:plaque_id>", methods=["POST"])
def admin_feature(plaque_id):
    if not is_admin():
        return jsonify({"ok": False, "error": "Not authenticated"}), 403
    with get_db() as db:
        # Ensure the plaque exists and is approved
        row = db.execute(
            "SELECT id FROM plaques WHERE id=? AND approved=1", (plaque_id,)
        ).fetchone()
        if not row:
            return jsonify({"ok": False, "error": "Plaque not found or not approved"}), 404
        # Clear any existing featured plaque, then set the new one — atomic
        with db:
            db.execute("UPDATE plaques SET is_featured=0")
            db.execute("UPDATE plaques SET is_featured=1 WHERE id=?", (plaque_id,))
    return jsonify({"ok": True, "featured_id": plaque_id})


# ── API ────────────────────────────────────────────────────────────────────────
@app.route("/api/plaques/geo")
def api_plaques_geo():
    """Lean GeoJSON for map pins — omits image URLs to minimise payload."""
    with get_db() as db:
        rows = db.execute(
            "SELECT id, slug, title, latitude, longitude"
            " FROM plaques WHERE approved=1 ORDER BY created_at DESC"
        ).fetchall()
    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [r["longitude"], r["latitude"]]},
            "properties": {
                "id": r["id"],
                "slug": r["slug"],
                "title": r["title"],
            },
        }
        for r in rows
    ]
    return jsonify({"type": "FeatureCollection", "features": features})


@app.route("/api/plaques")
def api_plaques():
    """Return all approved plaques as GeoJSON FeatureCollection."""
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM plaques WHERE approved=1 ORDER BY created_at DESC"
        ).fetchall()
    features = []
    for r in rows:
        d = plaque_to_dict(r)
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [d["longitude"], d["latitude"]]},
            "properties": d
        })
    return jsonify({"type": "FeatureCollection", "features": features})


@app.route("/api/search")
def api_search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])
    like = f"%{q}%"
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM plaques WHERE approved=1 "
            "AND (title LIKE ? OR description LIKE ?)"
            " ORDER BY created_at DESC LIMIT 30",
            (like, like)
        ).fetchall()
    return jsonify([plaque_to_dict(r) for r in rows])


@app.route("/admin/images/<int:plaque_id>/add", methods=["POST"])
def admin_image_add(plaque_id):
    if not is_admin():
        return jsonify({"ok": False, "error": "Not authenticated"}), 403
    f = request.files.get("image")
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "No image provided"}), 400
    ext = f.filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXT:
        return jsonify({"ok": False, "error": f"File type not allowed"}), 400
    with get_db() as db:
        count = db.execute("SELECT COUNT(*) FROM plaque_images WHERE plaque_id=?", (plaque_id,)).fetchone()[0]
        result = add_image_to_plaque(db, plaque_id, f, ext, is_primary=(count == 0), sort_order=count)
        if result["duplicate"]:
            return jsonify({"ok": False, "error": "Duplicate image — this photo is already attached to this plaque", "duplicate": True}), 409
        row = db.execute("SELECT id FROM plaque_images WHERE plaque_id=? ORDER BY id DESC LIMIT 1", (plaque_id,)).fetchone()
    return jsonify({"ok": True, "id": row["id"],
                    "image_url": image_url(result["image_file"]),
                    "thumb_url": thumb_url(result["thumb_file"]) or image_url(result["image_file"])})


@app.route("/admin/images/<int:image_id>/delete", methods=["POST"])
def admin_image_delete(image_id):
    if not is_admin():
        return jsonify({"ok": False, "error": "Not authenticated"}), 403
    with get_db() as db:
        img = db.execute("SELECT * FROM plaque_images WHERE id=?", (image_id,)).fetchone()
        if not img:
            return jsonify({"ok": False, "error": "Image not found"}), 404
        plaque_id = img["plaque_id"]
        count = db.execute("SELECT COUNT(*) FROM plaque_images WHERE plaque_id=?", (plaque_id,)).fetchone()[0]
        if count <= 1:
            return jsonify({"ok": False, "error": "Cannot delete the only image"}), 400
        for f, folder in [(img["image_file"], UPLOAD_DIR), (img["thumb_file"], THUMB_DIR)]:
            if f:
                try: os.remove(subdir_path(folder, f))
                except OSError: pass
        db.execute("DELETE FROM plaque_images WHERE id=?", (image_id,))
        if img["is_primary"]:
            db.execute("UPDATE plaque_images SET is_primary=1 WHERE plaque_id=? ORDER BY sort_order, id LIMIT 1", (plaque_id,))
            sync_primary_image(db, plaque_id)
    return jsonify({"ok": True})


@app.route("/admin/images/<int:image_id>/set-primary", methods=["POST"])
def admin_image_set_primary(image_id):
    if not is_admin():
        return jsonify({"ok": False, "error": "Not authenticated"}), 403
    with get_db() as db:
        img = db.execute("SELECT * FROM plaque_images WHERE id=?", (image_id,)).fetchone()
        if not img:
            return jsonify({"ok": False, "error": "Image not found"}), 404
        plaque_id = img["plaque_id"]
        db.execute("UPDATE plaque_images SET is_primary=0 WHERE plaque_id=?", (plaque_id,))
        db.execute("UPDATE plaque_images SET is_primary=1 WHERE id=?", (image_id,))
        sync_primary_image(db, plaque_id)
    return jsonify({"ok": True})


@app.route("/api/nearby/<int:plaque_id>")
def api_nearby(plaque_id):
    """Return the 10 nearest approved plaques to a given plaque, sorted by distance."""
    with get_db() as db:
        origin = db.execute(
            "SELECT latitude, longitude FROM plaques WHERE id=? AND approved=1",
            (plaque_id,),
        ).fetchone()
        if not origin:
            abort(404)

        # Rough bounding box (~200 km) to cut down candidates before haversine
        lat, lng = origin["latitude"], origin["longitude"]
        dlat = 1.8   # ~200 km in degrees latitude
        dlng = dlat / max(math.cos(math.radians(lat)), 0.01)

        candidates = db.execute(
            "SELECT * FROM plaques WHERE approved=1 AND id != ? "
            "AND latitude  BETWEEN ? AND ? "
            "AND longitude BETWEEN ? AND ? "
            "LIMIT 10",
            (plaque_id, lat - dlat, lat + dlat, lng - dlng, lng + dlng),
        ).fetchall()

    def haversine(lat1, lng1, lat2, lng2):
        R = 6371  # km
        dlat = math.radians(lat2 - lat1)
        dlng = math.radians(lng2 - lng1)
        a = (math.sin(dlat / 2) ** 2
             + math.cos(math.radians(lat1))
             * math.cos(math.radians(lat2))
             * math.sin(dlng / 2) ** 2)
        return R * 2 * math.asin(math.sqrt(a))

    ranked = sorted(
        candidates,
        key=lambda r: haversine(lat, lng, r["latitude"], r["longitude"]),
    )

    results = []
    for r in ranked:
        d = plaque_to_dict(r)
        d["distance_km"] = round(haversine(lat, lng, r["latitude"], r["longitude"]), 2)
        results.append(d)

    return jsonify(results)


@app.route("/api/plaques/<int:plaque_id>")
def api_plaque(plaque_id):
    with get_db() as db:
        row = db.execute(
            "SELECT * FROM plaques WHERE id=? AND approved=1", (plaque_id,)
        ).fetchone()
        if not row:
            abort(404)
        tags = get_tags_for_plaque(db, plaque_id)
    d = plaque_to_dict(row)
    d["tags"] = tags
    return jsonify(d)


# ── Upload / thumb file serving ────────────────────────────────────────────────
@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    fp = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(fp):
        return _placeholder_jpeg(filename), 200, {"Content-Type": "image/jpeg"}
    return send_from_directory(UPLOAD_DIR, filename)


@app.route("/thumbs/<path:filename>")
def thumb_file(filename):
    fp = os.path.join(THUMB_DIR, filename)
    if not os.path.exists(fp):
        return _placeholder_jpeg(filename), 200, {"Content-Type": "image/jpeg"}
    return send_from_directory(THUMB_DIR, filename)


def _placeholder_jpeg(filename: str) -> bytes:
    """Return a small colored JPEG placeholder — works in all browsers as <img> src."""
    palette = [
        (139, 115, 85),
        (107, 142, 107),
        (123, 107, 142),
        (142, 123, 107),
        (107, 139, 142),
    ]
    r, g, b = palette[sum(ord(c) for c in filename) % len(palette)]
    img = Image.new("RGB", (400, 300), color=(r, g, b))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=60)
    return buf.getvalue()




# Called at import time so Gunicorn/uWSGI/etc. initialise the DB on startup
init_db()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
