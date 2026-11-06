import unittest

from models import make_or_update_slug, parse_tags, path_to_lat_lng_zoom, slugify


class SlugHelpersTests(unittest.TestCase):
    def test_slugify_removes_punctuation_and_lowercases(self):
        self.assertEqual(slugify("The Plaque of 1912!"), "the-plaque-of-1912")
        self.assertEqual(slugify("  Café / Memorial  "), "cafe-memorial")

    def test_make_or_update_slug_adds_numeric_suffix_for_duplicates(self):
        class FakeDb:
            def __init__(self):
                self.rows = [
                    ("alpha", 1),
                    ("alpha-2", 2),
                ]

            def execute(self, sql, params=()):
                if sql.startswith("SELECT COUNT(*)"):
                    slug = params[0]
                    count = 1 if slug in {"alpha", "alpha-2"} else 0
                    return type("Row", (), {"fetchone": lambda self: type("Result", (), {"__getitem__": lambda self, key: count})()})()
                raise AssertionError(f"unexpected SQL: {sql}")

        db = FakeDb()
        self.assertEqual(make_or_update_slug(db, "Alpha"), "alpha-3")

    def test_parse_tags_strips_extra_whitespace_and_lowercases(self):
        self.assertEqual(parse_tags("  History, Memorial ,  War  "), ["history", "memorial", "war"])

    def test_path_to_lat_lng_zoom_clamps_and_defaults(self):
        self.assertEqual(path_to_lat_lng_zoom("37.3/-122.3/9", 0, 0, 1), (37.3, -122.3, 9))
        self.assertEqual(path_to_lat_lng_zoom("999/-999/99", 0, 0, 1), (90.0, -180.0, 19))
        self.assertEqual(path_to_lat_lng_zoom("", 10, 20, 3), (10.0, 20.0, 3))


if __name__ == "__main__":
    unittest.main()
