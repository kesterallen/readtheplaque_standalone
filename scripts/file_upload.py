
#!/usr/bin/env python3
"""Submit local images to Read The Plaque using a real browser."""

import argparse
from pathlib import Path

from playwright.sync_api import (
    sync_playwright,
    TimeoutError as PlaywrightTimeoutError,
)

URL = "https://readtheplaque-standalone.fly.dev/submit"
MAX_FILE_SIZE = 16 * 1024 * 1024


def main():
    parser = argparse.ArgumentParser(
        description="Submit photos of a plaque to Read The Plaque."
    )
    parser.add_argument("title", help="Title of the plaque")
    parser.add_argument("files", nargs="+", type=Path,
                        help="One or more local image files")
    parser.add_argument("--text", default="", help="Transcribed plaque text")
    parser.add_argument("--name", default="", help="Your name (optional)")
    parser.add_argument("--tags", default="", help="Comma-separated tags")
    parser.add_argument("--lat", help="Latitude (optional)")
    parser.add_argument("--lon", help="Longitude (optional)")
    args = parser.parse_args()

    paths = [p.expanduser().resolve() for p in args.files]

    for path in paths:
        if not path.is_file():
            parser.error(f"File does not exist: {path}")
        if path.stat().st_size > MAX_FILE_SIZE:
            parser.error(f"File exceeds 16 MB: {path}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(URL, wait_until="domcontentloaded")
        page.locator("#imageFile").set_input_files(
            [str(path) for path in paths]
        )

        # The visible labels on the site identify these text fields.
        page.get_by_label("Plaque Title").fill(args.title)

        if args.text:
            page.get_by_label("Plaque Text").fill(args.text)
        if args.name:
            page.get_by_label("Your Name").fill(args.name)
        if args.tags:
            page.get_by_label("Tags").fill(args.tags)
        if args.lat:
            page.get_by_label("Latitude").fill(args.lat)
        if args.lon:
            page.get_by_label("Longitude").fill(args.lon)

        print(f"\nPrepared {len(paths)} image(s) for submission.")
        print("Review the form in the browser.")
        print("Complete any required location or CAPTCHA steps.")
        print("Click 'Submit Plaque' when you're ready.")
        print("Close the browser when finished.")

        try:
            page.wait_for_event("close", timeout=0)
        except PlaywrightTimeoutError:
            pass
        finally:
            browser.close()


if __name__ == "__main__":
    main()

