"""
Read The Plaque — model helpers.

Pure helper functions for images, tags, and HTML sanitisation.
No Flask dependency — importable and testable without an app context.
"""

import hashlib
import io
import os
import sqlite3
import uuid
from typing import Optional

import bleach
from PIL import Image, ImageOps

from config import ALLOWED_TAGS, ALLOWED_ATTRS, THUMB_DIR, THUMB_SIZE, UPLOAD_DIR


# ── Filename helpers ───────────────────────────────────────────────────────────
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
    """Generate a UUID-based image filename."""
    return f"{uuid.uuid4().hex}.{ext}"


def new_thumb_filename() -> str:
    """Generate a UUID-based thumbnail filename."""
    return f"{uuid.uuid4().hex}_thumb.jpg"


# ── Thumbnail helpers ──────────────────────────────────────────────────────────
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
    """Create thumbnail from raw bytes."""
    try:
        with Image.open(io.BytesIO(img_bytes)) as img:
            return _save_thumbnail(img, thumb_filename)
    except Exception:
        return None


def _placeholder_jpeg(filename: str) -> bytes:
    """Return a small solid-colour JPEG placeholder for missing images."""
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


# ── URL helpers ────────────────────────────────────────────────────────────────
def _hex_subdir_url(prefix: str, filename: str) -> str:
    if len(filename) >= 2 and all(c in "0123456789abcdef" for c in filename[:2]):
        return f"/{prefix}/{filename[:2]}/{filename}"
    return f"/{prefix}/{filename}"


def image_url(filename: str) -> str:
    return _hex_subdir_url("uploads", filename)


def thumb_url(filename: Optional[str]) -> Optional[str]:
    if not filename:
        return None
    return _hex_subdir_url("thumbs", filename)


# ── Plaque dict ────────────────────────────────────────────────────────────────
def plaque_to_dict(row: sqlite3.Row) -> dict:
    """Convert a plaques table row to a plain dict with image_url/thumb_url added."""
    d = dict(row)
    d["image_url"] = image_url(d["image_file"])
    thumb = d.get("thumb_file")
    d["thumb_url"] = thumb_url(thumb) if thumb else d["image_url"]
    return d


# ── Image DB helpers ───────────────────────────────────────────────────────────
def get_images_for_plaque(db: sqlite3.Connection, plaque_id: int) -> list[dict]:
    """Return image dicts for a plaque, primary image first."""
    rows = db.execute(
        "SELECT * FROM plaque_images WHERE plaque_id=?"
        " ORDER BY is_primary DESC, sort_order ASC, id ASC",
        (plaque_id,),
    ).fetchall()
    return [dict(r) for r in rows]


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
    db.execute(
        "INSERT INTO plaque_images"
        " (plaque_id, image_file, thumb_file, image_hash, is_primary, sort_order)"
        " VALUES (?,?,?,?,?,?)",
        (
            plaque_id,
            filename,
            thumb_filename if thumb_ok else None,
            image_hash,
            1 if is_primary else 0,
            sort_order,
        ),
    )
    if is_primary:
        db.execute(
            "UPDATE plaques SET image_file=?, thumb_file=? WHERE id=?",
            (filename, thumb_filename if thumb_ok else None, plaque_id),
        )
    return {
        "image_file": filename,
        "thumb_file": thumb_filename if thumb_ok else None,
        "duplicate": False,
    }


def sync_primary_image(db: sqlite3.Connection, plaque_id: int) -> None:
    """Update plaques.image_file to match the current primary image."""
    primary = db.execute(
        "SELECT image_file, thumb_file FROM plaque_images"
        " WHERE plaque_id=? AND is_primary=1 LIMIT 1",
        (plaque_id,),
    ).fetchone()
    if not primary:
        primary = db.execute(
            "SELECT image_file, thumb_file FROM plaque_images"
            " WHERE plaque_id=? ORDER BY sort_order, id LIMIT 1",
            (plaque_id,),
        ).fetchone()
    if primary:
        db.execute(
            "UPDATE plaques SET image_file=?, thumb_file=? WHERE id=?",
            (primary["image_file"], primary["thumb_file"], plaque_id),
        )


# ── Tag helpers ────────────────────────────────────────────────────────────────
def get_tags_for_plaque(db: sqlite3.Connection, plaque_id: int) -> list[str]:
    """Return tag name strings for a plaque, sorted alphabetically."""
    rows = db.execute(
        "SELECT t.name FROM tags t"
        " JOIN plaque_tags pt ON pt.tag_id = t.id"
        " WHERE pt.plaque_id = ? ORDER BY t.name",
        (plaque_id,),
    ).fetchall()
    return [r["name"] for r in rows]


def set_tags_for_plaque(
    db: sqlite3.Connection, plaque_id: int, tag_names: list[str]
) -> None:
    """Replace all tags for a plaque with the given list."""
    db.execute("DELETE FROM plaque_tags WHERE plaque_id=?", (plaque_id,))
    for name in tag_names:
        name = name.strip().lower()
        if not name:
            continue
        db.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (name,))
        tag_id = db.execute("SELECT id FROM tags WHERE name=?", (name,)).fetchone()[
            "id"
        ]
        db.execute(
            "INSERT OR IGNORE INTO plaque_tags (plaque_id, tag_id) VALUES (?,?)",
            (plaque_id, tag_id),
        )


def parse_tags(raw: str) -> list[str]:
    """Parse a comma-separated tag string into a cleaned list."""
    return [t.strip().lower() for t in raw.split(",") if t.strip()]


# ── HTML sanitisation ──────────────────────────────────────────────────────────
def sanitise_description(raw: str) -> str:
    """Strip unsafe HTML from user-supplied description text.

    Allows a safe subset of formatting tags (bold, lists, links) while
    blocking XSS vectors (script, event handlers, javascript: hrefs, etc.).
    Returns an HTML-safe string ready to render with |safe in templates.
    """
    return bleach.clean(
        raw,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRS,
        strip=True,
        strip_comments=True,
    )
