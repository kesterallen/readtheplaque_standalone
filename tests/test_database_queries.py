import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import database
from database_queries import (
    count_plaques,
    get_featured_plaque,
    list_admin_plaque_page,
    list_approved_plaque_page,
    list_pending_page,
    list_submitter_page,
    list_tag_page,
    search_approved_plaques,
)


class DatabaseQueryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path_patch = patch.object(
            database, "DB_PATH", str(Path(self.temp_dir.name) / "queries.db")
        )
        self.db_path_patch.start()
        self.addCleanup(self.db_path_patch.stop)
        self.addCleanup(self.temp_dir.cleanup)
        database.init_db()

        with database.get_db() as db:
            db.executemany(
                "INSERT INTO plaques"
                " (slug, title, description, latitude, longitude, image_file, submitted_by, approved, is_featured)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    ("approved", "Approved plaque", "A history marker", 1, 2, "a.jpg", "Alice", 1, 1),
                    ("pending", "Pending plaque", "Waiting", 3, 4, "p.jpg", "Alice", 0, 0),
                    ("other", "Other plaque", "History too", 5, 6, "o.jpg", "Bob", 1, 0),
                ],
            )
            db.execute("INSERT INTO tags (name) VALUES (?)", ("history",))
            tag_id = db.execute(
                "SELECT id FROM tags WHERE name=?", ("history",)
            ).fetchone()["id"]
            plaque_id = db.execute(
                "SELECT id FROM plaques WHERE slug=?", ("approved",)
            ).fetchone()["id"]
            db.execute(
                "INSERT INTO plaque_tags (plaque_id, tag_id) VALUES (?, ?)",
                (plaque_id, tag_id),
            )

    def test_counts_and_featured_fallback(self):
        with database.get_db() as db:
            self.assertEqual(count_plaques(db), 3)
            self.assertEqual(count_plaques(db, approved=True), 2)
            self.assertEqual(count_plaques(db, approved=False), 1)
            self.assertEqual(get_featured_plaque(db)["slug"], "approved")

    def test_approved_and_pending_pages(self):
        with database.get_db() as db:
            approved = list_approved_plaque_page(db, limit=10, offset=0)
            pending_total, pending = list_pending_page(db, limit=10, offset=0)

        self.assertEqual([row["slug"] for row in approved], ["other", "approved"])
        self.assertEqual(pending_total, 1)
        self.assertEqual([row["slug"] for row in pending], ["pending"])

    def test_search_tag_and_submitter_queries(self):
        with database.get_db() as db:
            search_total, search_rows = search_approved_plaques(
                db, "history", limit=10, offset=0
            )
            tag_exists, tag_total, tag_rows = list_tag_page(
                db, "history", limit=10, offset=0
            )
            missing_exists, _, _ = list_tag_page(db, "absent", limit=10, offset=0)
            submitter_total, submitter_rows = list_submitter_page(
                db, "Alice", limit=10, offset=0
            )

        self.assertEqual(search_total, 2)
        self.assertEqual(len(search_rows), 2)
        self.assertTrue(tag_exists)
        self.assertEqual(tag_total, 1)
        self.assertEqual([row["slug"] for row in tag_rows], ["approved"])
        self.assertFalse(missing_exists)
        self.assertEqual(submitter_total, 1)
        self.assertEqual([row["slug"] for row in submitter_rows], ["approved"])

    def test_admin_sort_is_allowlisted_and_filters_are_parameterized(self):
        with database.get_db() as db:
            total, rows, sort, direction = list_admin_plaque_page(
                db,
                status="approved",
                query="plaque",
                sort="title; DROP TABLE plaques",
                direction="sideways",
                limit=10,
                offset=0,
            )
            tables_remain = db.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='plaques'"
            ).fetchone()[0]

        self.assertEqual(total, 2)
        self.assertEqual(len(rows), 2)
        self.assertEqual(sort, "created_at")
        self.assertEqual(direction, "desc")
        self.assertEqual(tables_remain, 1)


if __name__ == "__main__":
    unittest.main()
