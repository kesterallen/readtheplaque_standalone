"""Regression tests for proposed plaque fixes."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import database
from app import create_app


class ProposedPlaqueFixTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "proposed-fix-test-secret",
            "DATABASE": str(root / "test.db"),
            "UPLOAD_FOLDER": str(root / "uploads"),
            "THUMB_FOLDER": str(root / "thumbs"),
        })
        self.client = self.app.test_client()
        with self.app.app_context():
            with database.get_db() as db:
                cursor = db.execute(
                    """INSERT INTO plaques
                       (slug, title, description, latitude, longitude, image_file, approved)
                       VALUES (?, ?, ?, ?, ?, ?, 1)""",
                    ("test-plaque", "Test Plaque", "Description", 37.5, -122.2, "test.jpg"),
                )
                self.plaque_id = cursor.lastrowid
        self.addCleanup(self.temp_dir.cleanup)

    def fixes(self):
        with self.app.app_context():
            with database.get_db() as db:
                return db.execute(
                    "SELECT plaque_id, comment FROM proposed_plaque_fixes"
                ).fetchall()

    def test_public_submission_is_saved_and_shown_to_admin(self):
        response = self.client.post(
            "/plaque/test-plaque/propose-fix",
            data={"comment": "The location is incorrect."},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Thank you", response.get_data(as_text=True))
        rows = self.fixes()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["plaque_id"], self.plaque_id)
        self.assertEqual(rows[0]["comment"], "The location is incorrect.")

        with self.client.session_transaction() as session:
            session["admin"] = True
        listing = self.client.get("/admin/plaques")
        editing = self.client.get(f"/admin/edit/{self.plaque_id}")
        self.assertEqual(listing.status_code, 200)
        self.assertIn("Proposed fixes", listing.get_data(as_text=True))
        self.assertEqual(editing.status_code, 200)
        self.assertIn("The location is incorrect.", editing.get_data(as_text=True))


    def test_proposed_fix_requires_valid_hcaptcha_when_enabled(self):
        with patch("routes.public.captcha_enabled", return_value=True), patch(
            "routes.public.verify_captcha", return_value=(False, "CAPTCHA failed.")
        ) as verify:
            response = self.client.post(
                "/plaque/test-plaque/propose-fix",
                data={"comment": "Incorrect date.", "h-captcha-response": "bad-token"},
                follow_redirects=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn("CAPTCHA failed.", response.get_data(as_text=True))
        verify.assert_called_once_with("bad-token")
        self.assertEqual(self.fixes(), [])

    def test_proposed_fix_verifies_hcaptcha_token_when_enabled(self):
        with patch("routes.public.captcha_enabled", return_value=True), patch(
            "routes.public.verify_captcha", return_value=(True, "")
        ) as verify:
            response = self.client.post(
                "/plaque/test-plaque/propose-fix",
                data={"comment": "Incorrect date.", "h-captcha-response": "valid-token"},
                follow_redirects=True,
            )
        self.assertEqual(response.status_code, 200)
        verify.assert_called_once_with("valid-token")
        self.assertEqual(len(self.fixes()), 1)

    def test_blank_and_overlong_comments_are_rejected(self):
        for comment in ("   ", "x" * 2001):
            response = self.client.post(
                "/plaque/test-plaque/propose-fix", data={"comment": comment},
                follow_redirects=True,
            )
            self.assertEqual(response.status_code, 200)
        self.assertEqual(self.fixes(), [])

    def test_unknown_plaque_cannot_receive_a_fix(self):
        response = self.client.post(
            "/plaque/no-such-plaque/propose-fix", data={"comment": "Incorrect."}
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.fixes(), [])


    def test_admin_can_sort_by_proposed_fix_count(self):
        with self.app.app_context():
            with database.get_db() as db:
                db.execute(
                    """INSERT INTO plaques
                       (slug, title, description, latitude, longitude, image_file, approved)
                       VALUES (?, ?, ?, ?, ?, ?, 1)""",
                    ("no-fix-plaque", "No Fix Plaque", "Description", 37.6, -122.3, "other.jpg"),
                )
                db.execute(
                    "INSERT INTO proposed_plaque_fixes (plaque_id, comment) VALUES (?, ?)",
                    (self.plaque_id, "Needs correction."),
                )
        with self.client.session_transaction() as session:
            session["admin"] = True

        ascending = self.client.get("/admin/plaques?sort=proposed_fixes&dir=asc")
        descending = self.client.get("/admin/plaques?sort=proposed_fixes&dir=desc")
        self.assertLess(
            ascending.get_data(as_text=True).index("No Fix Plaque"),
            ascending.get_data(as_text=True).index("Test Plaque"),
        )
        self.assertLess(
            descending.get_data(as_text=True).index("Test Plaque"),
            descending.get_data(as_text=True).index("No Fix Plaque"),
        )

    def test_admin_can_clear_a_proposed_fix(self):
        with self.app.app_context():
            with database.get_db() as db:
                cursor = db.execute(
                    "INSERT INTO proposed_plaque_fixes (plaque_id, comment) VALUES (?, ?)",
                    (self.plaque_id, "Remove this report."),
                )
                fix_id = cursor.lastrowid
        with self.client.session_transaction() as session:
            session["admin"] = True

        response = self.client.post(
            f"/admin/proposed-fixes/{fix_id}/delete", follow_redirects=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.fixes(), [])
        self.assertNotIn("Remove this report.", response.get_data(as_text=True))


    def test_admin_list_summarizes_plaques_with_proposed_fixes(self):
        with self.app.app_context():
            with database.get_db() as db:
                db.execute(
                    """INSERT INTO plaques
                       (slug, title, description, latitude, longitude, image_file, approved)
                       VALUES (?, ?, ?, ?, ?, ?, 1)""",
                    ("second-plaque", "Second Plaque", "Description", 37.6, -122.3, "second.jpg"),
                )
                db.execute(
                    "INSERT INTO proposed_plaque_fixes (plaque_id, comment) VALUES (?, ?)",
                    (self.plaque_id, "Needs correction."),
                )
                db.execute(
                    "INSERT INTO proposed_plaque_fixes (plaque_id, comment) VALUES (?, ?)",
                    (self.plaque_id, "Another correction."),
                )
        with self.client.session_transaction() as session:
            session["admin"] = True

        response = self.client.get("/admin/plaques")
        self.assertEqual(response.status_code, 200)
        self.assertIn("1 plaque with proposed fixes", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
