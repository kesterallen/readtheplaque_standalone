"""Tests for the JSON API endpoints using an isolated SQLite database."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask

import database
from models import set_tags_for_plaque
from routes.api import api_bp


class ApiRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "test.db")
        self.db_path_patch = patch.object(database, "DB_PATH", self.db_path)
        self.db_path_patch.start()
        self.addCleanup(self.db_path_patch.stop)
        self.addCleanup(self.temp_dir.cleanup)

        database.init_db()
        app = Flask(
            __name__,
            template_folder=str(Path(__file__).resolve().parents[1] / "templates"),
        )
        app.config.update(TESTING=True, SECRET_KEY="test-secret")
        app.register_blueprint(api_bp)
        self.client = app.test_client()

    def insert_plaque(
        self,
        slug="approved-plaque",
        title="Approved Plaque",
        approved=1,
        latitude=37.5,
        longitude=-122.2,
        description="A historic marker",
    ):
        with database.get_db() as db:
            cursor = db.execute(
                """
                INSERT INTO plaques
                    (slug, title, description, latitude, longitude, image_file, approved)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    slug,
                    title,
                    description,
                    latitude,
                    longitude,
                    "abcdef123456.jpg",
                    approved,
                ),
            )
            return cursor.lastrowid

    def test_geojson_endpoint_returns_only_approved_plaques(self):
        self.insert_plaque()
        self.insert_plaque(
            slug="pending-plaque", title="Pending Plaque", approved=0
        )

        response = self.client.get("/api/plaques/geo")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["type"], "FeatureCollection")
        self.assertEqual(len(payload["features"]), 1)
        feature = payload["features"][0]
        self.assertEqual(feature["geometry"]["type"], "Point")
        self.assertEqual(feature["geometry"]["coordinates"], [-122.2, 37.5])
        self.assertEqual(feature["properties"]["slug"], "approved-plaque")

    def test_plaques_endpoint_returns_geojson_with_image_urls(self):
        self.insert_plaque()

        response = self.client.get("/api/plaques")

        self.assertEqual(response.status_code, 200)
        feature = response.get_json()["features"][0]
        self.assertEqual(feature["properties"]["title"], "Approved Plaque")
        self.assertEqual(
            feature["properties"]["image_url"], "/uploads/ab/abcdef123456.jpg"
        )

    def test_search_is_case_insensitive_and_excludes_pending_plaques(self):
        self.insert_plaque(title="Old Stone Memorial")
        self.insert_plaque(
            slug="pending-memorial",
            title="Pending Memorial",
            approved=0,
        )

        response = self.client.get("/api/search?q=MEMORIAL")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([p["title"] for p in response.get_json()], ["Old Stone Memorial"])

    def test_search_with_empty_query_returns_empty_list(self):
        self.insert_plaque()

        response = self.client.get("/api/search?q=%20")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), [])

    def test_search_treats_query_as_data_not_sql(self):
        self.insert_plaque()

        response = self.client.get("/api/search?q=%27%20OR%201%3D1%20--")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), [])

    def test_slug_endpoint_requires_title(self):
        response = self.client.get("/api/slug")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "title required"})

    def test_slug_endpoint_reports_existing_approved_slug(self):
        self.insert_plaque(slug="stone-memorial", title="Stone Memorial")

        response = self.client.get("/api/slug?title=Stone%20Memorial")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["base_slug"], "stone-memorial")
        self.assertEqual(payload["slug"], "stone-memorial-2")
        self.assertTrue(payload["exists"])
        self.assertEqual(payload["existing_title"], "Stone Memorial")
        self.assertEqual(payload["existing_url"], "/plaque/stone-memorial")

    def test_slug_endpoint_does_not_expose_pending_plaque_url(self):
        self.insert_plaque(
            slug="pending-memorial",
            title="Pending Memorial",
            approved=0,
        )

        response = self.client.get("/api/slug?title=Pending%20Memorial")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["exists"])
        self.assertEqual(payload["existing_title"], "Pending Memorial")
        self.assertIsNone(payload["existing_url"])

    def test_single_plaque_includes_tags(self):
        plaque_id = self.insert_plaque()
        with database.get_db() as db:
            set_tags_for_plaque(db, plaque_id, ["History", "Memorial"])

        response = self.client.get(f"/api/plaques/{plaque_id}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["tags"], ["history", "memorial"])

    def test_single_plaque_returns_404_for_pending_or_missing_plaque(self):
        pending_id = self.insert_plaque(
            slug="pending-plaque", title="Pending Plaque", approved=0
        )

        self.assertEqual(self.client.get(f"/api/plaques/{pending_id}").status_code, 404)
        self.assertEqual(self.client.get("/api/plaques/99999").status_code, 404)


if __name__ == "__main__":
    unittest.main()
