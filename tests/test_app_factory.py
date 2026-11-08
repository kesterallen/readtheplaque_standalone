"""Tests for the Flask application factory."""

import tempfile
import unittest
from pathlib import Path

from app import create_app


class AppFactoryTests(unittest.TestCase):
    def test_factory_uses_isolated_database_and_upload_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            app = create_app({
                "TESTING": True,
                "DATABASE": str(root / "test.db"),
                "UPLOAD_FOLDER": str(root / "uploads"),
                "SECRET_KEY": "test-secret",
            })

            self.assertTrue((root / "test.db").exists())
            self.assertTrue((root / "uploads").is_dir())
            self.assertEqual(app.config["SECRET_KEY"], "test-secret")
            self.assertEqual(app.test_client().get("/health").status_code, 200)

    def test_factory_registers_application_error_handlers(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            app = create_app({
                "TESTING": True,
                "DATABASE": str(root / "test.db"),
                "UPLOAD_FOLDER": str(root / "uploads"),
            })

            response = app.test_client().get("/not-a-real-page")

            self.assertEqual(response.status_code, 404)
            self.assertIn("error", response.get_data(as_text=True).lower())


if __name__ == "__main__":
    unittest.main()
