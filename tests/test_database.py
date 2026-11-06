import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import database
from models import get_tags_for_plaque, set_tags_for_plaque


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "test.db")
        self.db_path_patch = patch.object(database, "DB_PATH", self.db_path)
        self.db_path_patch.start()
        database.init_db()

    def tearDown(self):
        self.db_path_patch.stop()
        self.temp_dir.cleanup()

    def insert_plaque(self, db, slug="test-plaque"):
        cursor = db.execute(
            "INSERT INTO plaques (slug, title, latitude, longitude, image_file)"
            " VALUES (?, ?, ?, ?, ?)",
            (slug, "Test Plaque", 0.0, 0.0, "test.jpg"),
        )
        return cursor.lastrowid

    def test_init_db_creates_expected_tables(self):
        with closing(database.get_db()) as db:
            tables = {
                row[0]
                for row in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }

        self.assertTrue({"plaques", "tags", "plaque_tags", "plaque_images"} <= tables)

    def test_set_tags_replaces_existing_tags_and_normalizes_names(self):
        with closing(database.get_db()) as db:
            plaque_id = self.insert_plaque(db)
            set_tags_for_plaque(db, plaque_id, ["  History ", "MEMORIAL", ""])
            db.commit()
            self.assertEqual(
                get_tags_for_plaque(db, plaque_id), ["history", "memorial"]
            )

            set_tags_for_plaque(db, plaque_id, ["Architecture"])
            db.commit()
            self.assertEqual(get_tags_for_plaque(db, plaque_id), ["architecture"])

    def test_deleting_plaque_cascades_to_images(self):
        with closing(database.get_db()) as db:
            plaque_id = self.insert_plaque(db)
            db.execute(
                "INSERT INTO plaque_images (plaque_id, image_file) VALUES (?, ?)",
                (plaque_id, "test.jpg"),
            )
            db.execute("DELETE FROM plaques WHERE id=?", (plaque_id,))
            db.commit()
            count = db.execute("SELECT COUNT(*) FROM plaque_images").fetchone()[0]

        self.assertEqual(count, 0)

    def test_connection_enables_foreign_key_checks(self):
        with closing(database.get_db()) as db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute(
                    "INSERT INTO plaque_images (plaque_id, image_file) VALUES (?, ?)",
                    (9999, "orphan.jpg"),
                )


if __name__ == "__main__":
    unittest.main()
