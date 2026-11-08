"""Blueprint registration — imported once by app.py."""

from routes.admin import admin_bp
from routes.api import api_bp
from routes.public import public_bp
from routes.health import health_bp


def register_blueprints(app):
    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(health_bp)
