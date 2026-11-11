"""Regression tests for public-page pagination."""

import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import database
from app import create_app
from routes import public


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.hrefs.append(href)


class PublicPaginationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "pagination-test-secret",
            "DATABASE": str(root / "test.db"),
            "UPLOAD_FOLDER": str(root / "uploads"),
            "THUMB_FOLDER": str(root / "thumbs"),
        })
        self.client = self.app.test_client()
        self.per_page_patch = patch.object(public, "PER_PAGE", 2)
        self.per_page_patch.start()
        self.addCleanup(self.per_page_patch.stop)
        self.addCleanup(self.temp_dir.cleanup)

    def insert_plaque(
        self,
        slug,
        title,
        *,
        approved=1,
        featured=0,
        submitter="Test Submitter",
        created_at="2024-01-01 00:00:00",
        tagged=True,
    ):
        with self.app.app_context():
            with database.get_db() as db:
                cursor = db.execute(
                    """
                    INSERT INTO plaques
                        (slug, title, description, latitude, longitude,
                         image_file, approved, is_featured, submitted_by, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        slug, title, "Test description", 37.5, -122.2,
                        "abcdef123456.jpg", approved, featured, submitter, created_at,
                    ),
                )
                plaque_id = cursor.lastrowid
                if tagged:
                    db.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", ("history",))
                    tag_id = db.execute(
                        "SELECT id FROM tags WHERE name=?", ("history",)
                    ).fetchone()["id"]
                    db.execute(
                        "INSERT INTO plaque_tags (plaque_id, tag_id) VALUES (?, ?)",
                        (plaque_id, tag_id),
                    )
                return plaque_id

    @staticmethod
    def links_in(response):
        parser = LinkParser()
        parser.feed(response.get_data(as_text=True))
        return parser.hrefs

    def test_homepage_does_not_create_empty_last_page_when_recent_count_is_exact_multiple(self):
        # The featured plaque is displayed separately; four remaining plaques
        # fill exactly two pages at PER_PAGE=2.
        self.insert_plaque("featured", "Featured", featured=1)
        for number in range(4):
            self.insert_plaque(
                f"recent-{number}", f"Recent {number}",
                created_at=f"2024-01-0{number + 1} 00:00:00",
            )

        page_one = self.client.get("/")
        page_two = self.client.get("/page/2")
        self.assertEqual(page_one.status_code, 200)
        self.assertEqual(page_two.status_code, 200)
        page_one_html = page_one.get_data(as_text=True)
        page_two_html = page_two.get_data(as_text=True)

        # Page one links to page two; page two has no next-page link.
        self.assertIn('href="/?page=2"', page_one_html)
        self.assertNotIn('aria-label="Next"', page_two_html)
        self.assertEqual(page_two_html.count('class="plaque-card"'), 2)

    def test_path_page_number_takes_precedence_over_query_parameter(self):
        for number in range(5):
            self.insert_plaque(
                f"search-{number}", f"Searchable {number}",
                created_at=f"2024-01-0{number + 1} 00:00:00",
            )

        response = self.client.get("/search/2?q=Searchable&page=1")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        # The route's page=2 argument should select the second page, even
        # though the query string asks for page=1.
        self.assertIn("Searchable 2", html)
        self.assertIn("Searchable 1", html)
        self.assertNotIn("Searchable 4", html)
        self.assertEqual(html.count('class="plaque-card"'), 2)

    def test_search_pagination_preserves_and_encodes_special_query_characters(self):
        for number in range(3):
            self.insert_plaque(
                f"special-{number}", f"A&B + C {number}",
                created_at=f"2024-01-0{number + 1} 00:00:00",
            )

        response = self.client.get("/search?q=A%26B%20%2B%20C")
        self.assertEqual(response.status_code, 200)

        page_links = [
            href for href in self.links_in(response)
            if "page=" in href
        ]
        self.assertTrue(page_links)
        parsed = urlsplit(page_links[-1])
        self.assertEqual(parse_qs(parsed.query), {"q": ["A&B + C"], "page": ["2"]})

    def test_tag_and_submitter_pagination_use_valid_query_string_separator(self):
        for number in range(3):
            self.insert_plaque(
                f"filtered-{number}", f"Filtered {number}",
                submitter="A & B",
                created_at=f"2024-01-0{number + 1} 00:00:00",
            )

        tag_response = self.client.get("/tag/history")
        submitter_response = self.client.get("/submitter/A%20%26%20B")

        self.assertEqual(tag_response.status_code, 200)
        self.assertEqual(submitter_response.status_code, 200)

        for response in (tag_response, submitter_response):
            page_links = [
                href for href in self.links_in(response)
                if "page=" in href
            ]
            self.assertTrue(page_links)
            self.assertNotIn("?&", page_links[0])
            self.assertEqual(parse_qs(urlsplit(page_links[0]).query)["page"], ["2"])


if __name__ == "__main__":
    unittest.main()
