"""
Read The Plaque — application entry point.

create_app() builds a configured Flask application. The module-level app keeps
the conventional gunicorn app:app deployment command working.
"""

import os

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

from config import CARTO_API_KEY, DB_PATH, MAX_FILE_MB, MAX_UPLOAD_MB, SECRET_KEY, THUMB_DIR, UPLOAD_DIR
from database import init_db
from routes import register_blueprints


def create_app(test_config=None):
    """Create and configure the Flask application.

    test_config can override DATABASE, UPLOAD_FOLDER, secrets, and other
    Flask settings so tests can use isolated resources.
    """
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=SECRET_KEY,
        MAX_CONTENT_LENGTH=MAX_UPLOAD_MB * 1024 * 1024,
        MAX_FILE_MB=MAX_FILE_MB,
        MAX_UPLOAD_MB=MAX_UPLOAD_MB,
        UPLOAD_FOLDER=UPLOAD_DIR,
        THUMB_FOLDER=THUMB_DIR,
        DATABASE=DB_PATH,
    )
    if test_config:
        app.config.update(test_config)

    app.json.compact = True
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    register_blueprints(app)

    @app.errorhandler(RequestEntityTooLarge)
    def upload_too_large(_error):
        """Answer an oversized upload in a form the page can show (not Flask's HTML)."""
        message = (
            f"That upload is too large. A submission can be up to {app.config['MAX_UPLOAD_MB']} MB in "
            f"total ({app.config['MAX_FILE_MB']} MB per photo): please choose fewer or smaller photos."
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

    # Initialise the database when an application instance is created, not
    # merely because a module importing database helpers was loaded.
    with app.app_context():
        init_db()

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
