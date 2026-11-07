import unittest
from unittest.mock import patch

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
from helpers.pagination import clamp_page, paginate, total_pages


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class FakeDb:
    def __init__(self):
        self.statements = []

    def execute(self, sql, params=()):
        self.statements.append((sql, params))
        if sql.startswith("SELECT COUNT(*)"):
            return FakeResult([(1,)])
        if "FROM tags WHERE name" in sql:
            return FakeResult([(1,)])
        if "is_featured=1" in sql:
            return FakeResult([{"slug": "featured"}])
        return FakeResult([{"slug": "row"}])


class QueryAndPaginationHelperTests(unittest.TestCase):
    def test_pagination_normalizes_page_and_computes_page_count(self):
        self.assertEqual(clamp_page(-3), 1)
        self.assertEqual(clamp_page("not-a-number"), 1)
        self.assertEqual(paginate(3, 10), (3, 20))
        self.assertEqual(total_pages(0, 10), 1)
        self.assertEqual(total_pages(21, 10), 3)

    def test_public_query_helpers_use_placeholders_for_values(self):
        db = FakeDb()
        count_plaques(db, approved=True)
        get_featured_plaque(db)
        list_approved_plaque_page(db, limit=10, offset=0, exclude_id=5)
        search_approved_plaques(db, "x%' OR 1=1 --", limit=10, offset=0)
        list_tag_page(db, "history", limit=10, offset=0)
        list_submitter_page(db, "Alice", limit=10, offset=0)
        list_pending_page(db, limit=10, offset=0)

        for sql, params in db.statements:
            if params:
                self.assertIn("?", sql)
        search_call = next(
            (sql, params)
            for sql, params in db.statements
            if "title LIKE" in sql
        )
        self.assertNotIn("OR 1=1", search_call[0])
        self.assertIn("OR 1=1", search_call[1][0])

    def test_admin_sort_columns_and_directions_are_normalized(self):
        db = FakeDb()
        total, rows, sort, direction = list_admin_plaque_page(
            db,
            status="approved",
            query="marker",
            sort="title; DROP TABLE plaques",
            direction="sideways",
            limit=10,
            offset=0,
        )

        self.assertEqual(total, 1)
        self.assertEqual(sort, "created_at")
        self.assertEqual(direction, "desc")
        query_sql, query_params = db.statements[-1]
        self.assertIn("ORDER BY created_at DESC", query_sql)
        self.assertEqual(query_params[-2:], (10, 0))


if __name__ == "__main__":
    unittest.main()
