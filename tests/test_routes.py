import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask

import database
from routes import api, public


class RouteCoverageTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "test.db")
        self.db_path_patch = patch.object(database, "DB_PATH", self.db_path)
        self.db_path_patch.start()

        database.init_db()

        with database.get_db() as db:
            db.execute(
                "INSERT INTO plaques (slug, title, description, latitude, longitude, image_file, thumb_file, submitted_by, approved)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "test-plaque",
                    "Test Plaque",
                    "A plaque for testing.",
                    51.5074,
                    -0.1278,
                    "abc123.jpg",
                    "abc123_thumb.jpg",
                    "Test User",
                    1,
                ),
            )
            plaque_id = db.execute("SELECT id FROM plaques WHERE slug=?", ("test-plaque",)).fetchone()["id"]
            db.execute("INSERT INTO tags (name) VALUES (?)", ("history",))
            tag_id = db.execute("SELECT id FROM tags WHERE name=?", ("history",)).fetchone()["id"]
            db.execute(
                "INSERT INTO plaque_tags (plaque_id, tag_id) VALUES (?, ?)",
                (plaque_id, tag_id),
            )
            db.execute(
                "INSERT INTO plaque_images (plaque_id, image_file, thumb_file, is_primary, sort_order)"
                " VALUES (?, ?, ?, ?, ?)",
                (plaque_id, "abc123.jpg", "abc123_thumb.jpg", 1, 0),
            )

        self.app = Flask(__name__)
        self.app.secret_key = "test-secret"
        self.app.register_blueprint(public.public_bp)
        self.app.register_blueprint(api.api_bp)
        self.client = self.app.test_client()

    def tearDown(self):
        self.db_path_patch.stop()
        self.temp_dir.cleanup()

    def test_public_pages_render(self):
        for path in [
            "/",
            "/rss",
            "/map",
            "/search?q=history",
            "/plaque/test-plaque",
            "/tag/history",
            "/submitter/Test%20User",
            "/about",
            "/counts",
        ]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)

    def test_random_redirects_to_approved_plaque(self):
        response = self.client.get("/random", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/plaque/test-plaque"))

    def test_api_endpoints_return_expected_payloads(self):
        geo = self.client.get("/api/plaques/geo")
        self.assertEqual(geo.status_code, 200)
        geo_data = geo.get_json()
        self.assertIn("features", geo_data)
        self.assertGreaterEqual(len(geo_data["features"]), 1)

        all_plaques = self.client.get("/api/plaques")
        self.assertEqual(all_plaques.status_code, 200)
        self.assertIn("features", all_plaques.get_json())

        search = self.client.get("/api/search?q=history")
        self.assertEqual(search.status_code, 200)
        self.assertIsInstance(search.get_json(), list)
        self.assertGreaterEqual(len(search.get_json()), 1)

        nearby = self.client.get("/api/nearby/51.5074/-0.1278")
        self.assertEqual(nearby.status_code, 200)
        self.assertIsInstance(nearby.get_json(), list)

        plaque = self.client.get("/api/plaques/1")
        self.assertEqual(plaque.status_code, 200)
        self.assertEqual(plaque.get_json()["slug"], "test-plaque")

        slug_check = self.client.get("/api/slug?title=Test Plaque")
        self.assertEqual(slug_check.status_code, 200)
        self.assertIn("slug", slug_check.get_json())


if __name__ == "__main__":
    unittest.main()
