"""
Read The Plaque — application entry point.

Creates the Flask app, registers blueprints, and initialises the database.
All routes live in routes/, helpers in models.py, config in config.py,
and DB setup in database.py.
"""

import os

from flask import Flask

from config import MAX_MB, SECRET_KEY, UPLOAD_DIR
from database import init_db
from routes import register_blueprints

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = MAX_MB * 1024 * 1024
app.config["UPLOAD_FOLDER"] = UPLOAD_DIR
app.json.compact = True

os.makedirs(UPLOAD_DIR, exist_ok=True)

register_blueprints(app)

# Initialise DB at import time so Gunicorn picks it up on startup
init_db()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
