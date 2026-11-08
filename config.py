"""
Read The Plaque — environment-backed configuration.

Keep defaults suitable for local development, but never ship a known secret or
default administrator password in production.
"""

import os
from pathlib import Path


def _env_int(name: str, default: int) -> int:
    """Read a positive integer environment setting with a useful error."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be greater than zero")
    return value


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# ── Environment ────────────────────────────────────────────────────────────────
APP_ENV = os.environ.get("APP_ENV", "").strip().lower()
IS_PRODUCTION = APP_ENV == "production" or bool(os.environ.get("FLY_APP_NAME"))
DEBUG = _env_bool("DEBUG", False) and not IS_PRODUCTION

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR = str(Path(__file__).resolve().parent)
DEFAULT_DATA_DIR = "/data" if os.path.isdir("/data") else BASE_DIR
DATA_DIR = os.environ.get("DATA_DIR", DEFAULT_DATA_DIR)

DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(DATA_DIR, "plaques.db"))
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", os.path.join(DATA_DIR, "uploads"))
THUMB_DIR = os.environ.get("THUMB_DIR", os.path.join(DATA_DIR, "thumbs"))

# ── Image settings ─────────────────────────────────────────────────────────────
THUMB_SIZE = (400, 300)
ALLOWED_EXT = {"png", "jpg", "jpeg", "gif", "webp"}
MAX_FILE_MB = _env_int("MAX_FILE_MB", 16)
# Reject images whose decoded pixel count could consume excessive memory.
MAX_IMAGE_PIXELS = _env_int("MAX_IMAGE_PIXELS", 40_000_000)
MAX_UPLOAD_MB = _env_int("MAX_UPLOAD_MB", 100)

# ── App behaviour ─────────────────────────────────────────────────────────────
NEARBY_LIMIT = _env_int("NEARBY_LIMIT", 10)
PER_PAGE = _env_int("PER_PAGE", 24)

# ── Secrets and admin authentication ──────────────────────────────────────────
# Set SECRET_KEY to a long, random value in production.
SECRET_KEY = os.environ.get("SECRET_KEY")
# Prefer ADMIN_PASSWORD_HASH (Werkzeug generate_password_hash format). The
# plaintext ADMIN_PASSWORD variable remains supported for backwards compatibility.
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH")
TRUSTED_HOSTS = [
    host.strip()
    for host in os.environ.get("TRUSTED_HOSTS", "").split(",")
    if host.strip()
]
TRUST_PROXY_HEADERS = _env_bool("TRUST_PROXY_HEADERS", IS_PRODUCTION)

# ── Session and request limits ─────────────────────────────────────────────────
SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", IS_PRODUCTION)
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
MAX_CONTENT_LENGTH = MAX_UPLOAD_MB * 1024 * 1024

# ── HTML sanitisation allowlist ────────────────────────────────────────────────
ALLOWED_TAGS: list[str] = [
    "b", "i", "em", "strong", "u", "s", "del", "p", "br", "ul", "ol",
    "li", "blockquote", "h3", "h4", "h5", "h6", "a", "pre", "code",
]
ALLOWED_ATTRS: dict[str, list[str]] = {"a": ["href", "title"]}

# ── Map tiles ──────────────────────────────────────────────────────────────────
CARTO_API_KEY = os.environ.get("CARTO_API_KEY", "")

# ── Link previews ──────────────────────────────────────────────────────────────
SITE_URL = os.environ.get("SITE_URL", "").rstrip("/")
SHARE_IMAGE_MAX_MB = _env_int("SHARE_IMAGE_MAX_MB", 4)

# ── Spam / hCaptcha ────────────────────────────────────────────────────────────
HCAPTCHA_SITEKEY = os.environ.get("HCAPTCHA_SITEKEY", "")
HCAPTCHA_SECRET = os.environ.get("HCAPTCHA_SECRET", "")
HCAPTCHA_VERIFY_URL = "https://api.hcaptcha.com/siteverify"

RATE_LIMIT_MAX = _env_int("RATE_LIMIT_MAX", 5)
RATE_LIMIT_WINDOW = _env_int("RATE_LIMIT_WINDOW", 3600)
