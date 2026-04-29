"""
Read The Plaque — spam / abuse prevention helpers.

Layers:
  1. hCaptcha    — human verification widget (skipped in dev if secret unset)
  2. Honeypot    — hidden form field that bots fill, humans don't
  3. Rate limit  — in-memory per-IP submission counter with a rolling window
  4. Content     — block obvious URL spam in title / description
"""

import time
import re
import urllib.request
import urllib.parse
import json
from collections import defaultdict
from threading import Lock

from config import (
    HCAPTCHA_SECRET,
    HCAPTCHA_SITEKEY,
    HCAPTCHA_VERIFY_URL,
)

# ── hCaptcha ───────────────────────────────────────────────────────────────────


def captcha_enabled() -> bool:
    """Return True when a real hCaptcha secret is configured."""
    return bool(HCAPTCHA_SECRET)


def verify_captcha(token: str) -> tuple[bool, str]:
    """Verify an hCaptcha response token with the hCaptcha API.

    Returns (ok, error_message).  Always passes when captcha is disabled
    (no secret configured) so dev/test flows are unaffected.
    """
    if not captcha_enabled():
        return True, ""
    if not token:
        return False, "Please complete the CAPTCHA."
    try:
        payload = urllib.parse.urlencode(
            {"secret": HCAPTCHA_SECRET, "response": token}
        ).encode()
        req = urllib.request.Request(
            HCAPTCHA_VERIFY_URL,
            data=payload,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read())
        if result.get("success"):
            return True, ""
        codes = result.get("error-codes", [])
        return False, f"CAPTCHA failed ({', '.join(codes)}). Please try again."
    except Exception:
        # Network hiccup — fail open rather than block real users
        return True, ""


# ── Honeypot ───────────────────────────────────────────────────────────────────

HONEYPOT_FIELD = "website"  # rendered as display:none; bots fill it, humans don't


def check_honeypot(form_data) -> bool:
    """Return True (spam detected) if the hidden honeypot field has a value."""
    return bool(form_data.get(HONEYPOT_FIELD, "").strip())


# ── Rate limiting (in-memory, per IP) ─────────────────────────────────────────
# Uses a simple sliding-window counter stored in a module-level dict.
# This is per-process; on multi-worker Gunicorn each worker has its own counter.
# Good enough for a low-traffic community site — no Redis dependency needed.

_rate_lock = Lock()
_rate_store: dict[str, list[float]] = defaultdict(list)


# ── Content checks ─────────────────────────────────────────────────────────────

# URLs in title are almost always spam
_URL_RE = re.compile(r"https?://|www\.", re.IGNORECASE)

# Common spam keywords (extend as needed)
_SPAM_WORDS = re.compile(
    r"\b(casino|viagra|cialis|porn|xxx|crypto|bitcoin|nft|loan|payday|seo\s+service|buy\s+followers)\b",
    re.IGNORECASE,
)


def check_content(title: str, description: str) -> tuple[bool, str]:
    """Return (ok, error_message). Blocks obvious URL/keyword spam."""
    if _URL_RE.search(title):
        return False, "Title may not contain URLs."
    if _SPAM_WORDS.search(title) or _SPAM_WORDS.search(description):
        return False, "Submission contains disallowed content."
    return True, ""
