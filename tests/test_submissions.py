import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask
from PIL import Image

import database
import models
from routes import public


class SubmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.db_path = str(root / "test.db")
        self.upload_dir = str(root / "uploads")
        self.thumb_dir = str(root / "thumbs")

        self.patches = [
            patch.object(database, "DB_PATH", self.db_path),
            patch.object(public, "UPLOAD_DIR", self.upload_dir),
            patch.object(models, "UPLOAD_DIR", self.upload_dir),
            patch.object(models, "THUMB_DIR", self.thumb_dir),
            patch.object(public, "check_honeypot", return_value=False),
            patch.object(public, "check_rate_limit", return_value=(True, None)),
            patch.object(public, "verify_captcha", return_value=(True, None)),
            patch.object(public, "check_content", return_value=(True, None)),
        ]
        for active_patch in self.patches:
            active_patch.start()
            self.addCleanup(active_patch.stop)

        database.init_db()
        self.app = Flask(__name__)
        self.app.secret_key = "test-secret"
        self.app.register_blueprint(public.public_bp)
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    @staticmethod
    def jpeg_bytes():
        image = Image.new("RGB", (8, 8), color="red")
        output = io.BytesIO()
        image.save(output, format="JPEG")
        output.seek(0)
        return output

    def post_submission(self, image_bytes=None, filename="plaque.jpg", **form):
        data = {
            "title": "Test Memorial",
            "latitude": "37.5",
            "longitude": "-122.2",
            "description": "A short inscription",
            "submitted_by": "Test User",
            "tags": "history, memorial",
            **form,
        }
        if image_bytes is not None:
            data["images"] = (image_bytes, filename)
        return self.client.post("/submit", data=data, content_type="multipart/form-data")

    def test_valid_submission_creates_pending_plaque_image_and_tags(self):
        response = self.post_submission(self.jpeg_bytes())

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["pending"])
        self.assertEqual(payload["lat"], 37.5)
        self.assertEqual(payload["lng"], -122.2)

        with database.get_db() as db:
            plaque = db.execute(
                "SELECT id, slug, approved, image_file FROM plaques"
            ).fetchone()
            image = db.execute(
                "SELECT plaque_id, is_primary FROM plaque_images"
            ).fetchone()
            tags = db.execute("SELECT name FROM tags ORDER BY name").fetchall()

        self.assertIsNotNone(plaque)
        self.assertEqual(plaque["slug"], "test-memorial")
        self.assertEqual(plaque["approved"], 0)
        self.assertTrue(Path(self.upload_dir, plaque["image_file"][:2], plaque["image_file"]).is_file())
        self.assertEqual(image["plaque_id"], plaque["id"])
        self.assertEqual(image["is_primary"], 1)
        self.assertEqual([tag["name"] for tag in tags], ["history", "memorial"])

    def test_submission_without_photo_is_rejected_without_database_changes(self):
        response = self.post_submission()

        self.assertEqual(response.status_code, 400)
        self.assertIn("At least one image is required.", response.get_json()["errors"])
        with database.get_db() as db:
            count = db.execute("SELECT COUNT(*) FROM plaques").fetchone()[0]
        self.assertEqual(count, 0)

    def test_duplicate_photo_is_rejected_without_creating_second_plaque(self):
        first = self.post_submission(self.jpeg_bytes())
        second = self.post_submission(self.jpeg_bytes(), title="Another Plaque")

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 400)
        self.assertTrue(any("duplicate" in error.lower() for error in second.get_json()["errors"]))
        with database.get_db() as db:
            count = db.execute("SELECT COUNT(*) FROM plaques").fetchone()[0]
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
