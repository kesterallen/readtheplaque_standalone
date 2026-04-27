"""
Read The Plaque — application configuration.

All paths, constants, and environment-sourced settings live here so they can
be imported by any module without touching the Flask app object.
"""

import os

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# On Fly.io (and similar) a persistent volume is mounted at /data.
# Store the DB and uploads there so they survive redeploys.
_DATA_DIR = "/data" if os.path.isdir("/data") else BASE_DIR

DB_PATH = os.path.join(_DATA_DIR, "plaques.db")
UPLOAD_DIR = os.path.join(_DATA_DIR, "uploads")
THUMB_DIR = os.path.join(_DATA_DIR, "thumbs")

# ── Image settings ─────────────────────────────────────────────────────────────
THUMB_SIZE = (400, 300)
ALLOWED_EXT = {"png", "jpg", "jpeg", "gif", "webp"}
MAX_MB = 16

# ── App behaviour ──────────────────────────────────────────────────────────────
NEARBY_LIMIT = 10
PER_PAGE = 12
PER_PAGE_ADMIN = 24

# ── Secrets (override via environment in production) ──────────────────────────
# TODO: Change these in production!
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "plaqueadmin")
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")

# ── HTML sanitisation allowlist ────────────────────────────────────────────────
ALLOWED_TAGS: list[str] = [
    "b",
    "i",
    "em",
    "strong",
    "u",
    "s",
    "del",
    "p",
    "br",
    "ul",
    "ol",
    "li",
    "blockquote",
    "h3",
    "h4",
    "h5",
    "h6",
    "a",
    "pre",
    "code",
]
ALLOWED_ATTRS: dict[str, list[str]] = {
    "a": ["href", "title"],
}
