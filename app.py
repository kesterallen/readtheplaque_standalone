"""
Read The Plaque — Flask application factory and WSGI entry point.
"""

import os
import secrets

from flask import Flask, jsonify, render_template, request
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

from config import (
    APP_ENV,
    CARTO_API_KEY,
    DB_PATH,
    DEBUG,
    IS_PRODUCTION,
    MAX_CONTENT_LENGTH,
    MAX_FILE_MB,
    MAX_IMAGE_PIXELS,
    MAX_UPLOAD_MB,
    SECRET_KEY,
    SESSION_COOKIE_HTTPONLY,
    SESSION_COOKIE_SAMESITE,
    SESSION_COOKIE_SECURE,
    THUMB_DIR,
    TRUSTED_HOSTS,
    TRUST_PROXY_HEADERS,
    UPLOAD_DIR,
)
from database import init_db
from routes import register_blueprints


def create_app(test_config=None):
    """Create and configure the Flask application.

    Pass DATABASE, UPLOAD_FOLDER, THUMB_FOLDER, and TESTING overrides through
    test_config to isolate tests and local instances.
    """
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=SECRET_KEY or (None if IS_PRODUCTION else secrets.token_hex(32)),
        MAX_CONTENT_LENGTH=MAX_CONTENT_LENGTH,
        MAX_FILE_MB=MAX_FILE_MB,
        MAX_IMAGE_PIXELS=MAX_IMAGE_PIXELS,
        MAX_UPLOAD_MB=MAX_UPLOAD_MB,
        UPLOAD_FOLDER=UPLOAD_DIR,
        THUMB_FOLDER=THUMB_DIR,
        DATABASE=DB_PATH,
        SESSION_COOKIE_SECURE=SESSION_COOKIE_SECURE,
        SESSION_COOKIE_HTTPONLY=SESSION_COOKIE_HTTPONLY,
        SESSION_COOKIE_SAMESITE=SESSION_COOKIE_SAMESITE,
        TRUSTED_HOSTS=TRUSTED_HOSTS or None,
    )
    if test_config:
        app.config.update(test_config)

    if not app.config.get("SECRET_KEY"):
        raise RuntimeError(
            "SECRET_KEY must be set to a random, private value in production."
        )

    app.json.compact = True
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(app.config["THUMB_FOLDER"], exist_ok=True)

    # Only enable ProxyFix when the app is behind a known, trusted proxy.
    # Fly.io supplies one proxy hop; do not enable this on direct deployments.
    if TRUST_PROXY_HEADERS:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=0)

    register_blueprints(app)

    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(self)")
        if request.is_secure:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response

    @app.errorhandler(RequestEntityTooLarge)
    def upload_too_large(_error):
        """Return an upload error in the JSON format used by the submit page."""
        message = (
            f"That upload is too large. A submission can be up to {app.config['MAX_UPLOAD_MB']} MB "
            f"in total ({app.config['MAX_FILE_MB']} MB per photo): "
            "please choose fewer or smaller photos."
        )
        if request.path == "/submit" or request.path.startswith("/admin/images/"):
            return jsonify({"ok": False, "errors": [message], "error": message}), 413
        return message, 413

    @app.errorhandler(HTTPException)
    def handle_http_error(error):
        """Render friendly HTML for browser 4xx errors and JSON for API clients."""
        if not 400 <= error.code < 500:
            return error

        titles = {
            400: "That request didn’t work",
            401: "Please sign in",
            403: "You can’t go that way",
            404: "We can’t find that plaque",
            405: "That action isn’t available",
            408: "That took too long",
            410: "This page has moved on",
            413: "That upload is too large",
            414: "That address is too long",
            415: "That file type isn’t supported",
            422: "We couldn’t process that",
            429: "You’re making requests too quickly",
        }
        messages = {
            400: "Something about that request was invalid. Please check the address and try again.",
            401: "You’ll need to sign in before you can view this page.",
            403: "This part of the site isn’t available to you.",
            404: "The page may have moved, or the address might be mistyped. The plaques are still out there.",
            405: "This page doesn’t support that action. Try going back or heading to the map.",
            408: "The request took too long to complete. Please try again.",
            410: "This page is no longer available, but there are plenty more plaques to explore.",
            413: "The upload is larger than this site can accept. Try fewer or smaller photos.",
            414: "The address is too long to open. Try returning to the site and navigating from there.",
            415: "Please choose a file in a supported format and try again.",
            422: "The information couldn’t be processed. Please check it and try again.",
            429: "Please wait a moment before trying again.",
        }

        if request.path.startswith("/api/"):
            payload = {
                "error": titles.get(error.code, "Request error"),
                "message": messages.get(error.code, "The request could not be completed."),
                "status": error.code,
            }
            return jsonify(payload), error.code

        return render_template(
            "error.html",
            status=error.code,
            title=titles.get(error.code, "Something went wrong"),
            message=messages.get(error.code, "We couldn’t complete that request. Please try again."),
        ), error.code

    @app.context_processor
    def inject_globals():
        return {"carto_api_key": CARTO_API_KEY}

    # Initialise the database after configuration is applied.
    with app.app_context():
        init_db()

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=DEBUG, host="0.0.0.0", port=5000)
