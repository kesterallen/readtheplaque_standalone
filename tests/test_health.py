"""Tests for the application health endpoint."""

import unittest
from unittest.mock import patch

from flask import Flask

from routes.health import health_bp


class HealthRouteTests(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.config.update(TESTING=True)
        app.register_blueprint(health_bp)
        self.client = app.test_client()

    def test_health_returns_ok_when_database_is_available(self):
        with patch("routes.health.get_db") as get_db:
            get_db.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = (1,)

            response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})

    def test_health_returns_503_when_database_is_unavailable(self):
        with patch("routes.health.get_db", side_effect=RuntimeError("database down")):
            response = self.client.get("/health")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.get_json(),
            {"status": "error", "database": "unavailable"},
        )


if __name__ == "__main__":
    unittest.main()
