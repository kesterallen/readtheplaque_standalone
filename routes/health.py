"""Health endpoint used by Fly.io and external uptime monitors."""

from flask import Blueprint, current_app, jsonify

from database import get_db

health_bp = Blueprint("health", __name__)


@health_bp.get("/health")
def health():
    """Return 200 only when the application can also reach its database."""
    try:
        with get_db() as db:
            db.execute("SELECT 1").fetchone()
    except Exception:
        current_app.logger.exception("Health check failed: database unavailable")
        return jsonify({"status": "error", "database": "unavailable"}), 503

    return jsonify({"status": "ok"}), 200
