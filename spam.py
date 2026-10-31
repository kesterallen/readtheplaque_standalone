"""
Read The Plaque — spam / abuse prevention helpers.

Layers:
  1. hCaptcha    — human verification widget (skipped in dev if secret unset)
  2. Honeypot    — hidden form field that bots fill, humans don't
  3. Rate limit  — in-memory per-IP submission counter with a rolling window
  4. Content     — block obvious URL spam in title / description
"""

import logging
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
    RATE_LIMIT_MAX,
    RATE_LIMIT_WINDOW,
)

log = logging.getLogger(__name__)

# ── hCaptcha ───────────────────────────────────────────────────────────────────


def captcha_enabled() -> bool:
    """True only when BOTH hCaptcha keys are configured.

    The site key makes the widget appear; the secret makes the server enforce it.
    Enforcing without a widget would reject every submission with nothing for the
    visitor to solve, so a half-configured captcha stays off (and is logged).
    """
    return bool(HCAPTCHA_SECRET and HCAPTCHA_SITEKEY)


def _warn_if_half_configured() -> None:
    if bool(HCAPTCHA_SECRET) != bool(HCAPTCHA_SITEKEY):
        missing = "HCAPTCHA_SITEKEY" if HCAPTCHA_SECRET else "HCAPTCHA_SECRET"
        log.warning(
            "hCaptcha is only half-configured (%s is not set): the captcha is OFF. "
            "Set both HCAPTCHA_SITEKEY and HCAPTCHA_SECRET to enable it.",
            missing,
        )


_warn_if_half_configured()


def verify_captcha(token: str) -> tuple[bool, str]:
    """Verify an hCaptcha response token with the hCaptcha API.

    Returns (ok, error_message).  Always passes when captcha is disabled
    (no secret configured) so dev/test flows are unaffected.
    """
    if not captcha_enabled():
        return True, ""
    if not token:
        # The page itself says "Please complete the CAPTCHA." when the widget is
        # unsolved; reaching here means the response never arrived at all (e.g. a
        # stale cached page from before a deploy), so ask for a reload instead.
        return False, "The CAPTCHA response didn't reach the server. Please reload the page and try again."
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
    except Exception as exc:
        # Network hiccup — fail open rather than block real users. But say so:
        # otherwise a broken verifier silently turns the captcha off.
        log.warning("hCaptcha verification unavailable; allowing submission: %r", exc)
        return True, ""


# ── Rate limiting (in-memory, per IP) ────────────────────────────────────────
# Uses a simple sliding-window counter stored in a module-level dict.
# Per-process only — on multi-worker Gunicorn each worker has its own counter,
# which is good enough for a low-traffic community site.

_rate_lock = Lock()
_rate_store: dict[str, list[float]] = defaultdict(list)


def check_rate_limit(ip: str) -> tuple[bool, str]:
    """Return (allowed, error_message).

    Allows up to RATE_LIMIT_MAX submissions per IP within RATE_LIMIT_WINDOW seconds.
    """
    now = time.monotonic()
    cutoff = now - RATE_LIMIT_WINDOW
    with _rate_lock:
        timestamps = [t for t in _rate_store[ip] if t > cutoff]
        if len(timestamps) >= RATE_LIMIT_MAX:
            wait = int(RATE_LIMIT_WINDOW - (now - timestamps[0]))
            return False, f"Too many submissions. Please wait {wait // 60 + 1} minute(s)."
        timestamps.append(now)
        _rate_store[ip] = timestamps
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
    r"\b(viagra|cialis|porn|xxx|crypto|bitcoin|nft|seo\s+service|buy\s+followers)\b",
    re.IGNORECASE,
)


def check_content(title: str, description: str) -> tuple[bool, str]:
    """Return (ok, error_message). Blocks obvious URL/keyword spam."""
    if _URL_RE.search(title):
        return False, "Title may not contain URLs."
    if _SPAM_WORDS.search(title) or _SPAM_WORDS.search(description):
        return False, "Submission contains disallowed content."
    return True, ""
