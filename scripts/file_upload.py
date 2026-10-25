
#!/usr/bin/env python3
"""Prepare a Read The Plaque submission with optional EXIF GPS detection."""

import argparse
from pathlib import Path

from PIL import Image, ExifTags
from playwright.sync_api import sync_playwright

URL = "https://readtheplaque.com/submit"
MAX_FILE_SIZE = 16 * 1024 * 1024

GPS_IFD = ExifTags.IFD.GPSInfo


def dms_to_decimal(dms, ref):
    """Convert EXIF degrees/minutes/seconds to decimal coordinates."""
    degrees, minutes, seconds = (float(v) for v in dms)
    result = degrees + minutes / 60 + seconds / 3600

    if ref in ("S", "W"):
        result = -result

    return result


def get_exif_gps(path):
    """Return (latitude, longitude), or None if GPS EXIF is unavailable."""
    try:
        with Image.open(path) as image:
            exif = image.getexif()

            if not exif:
                return None

            gps = exif.get_ifd(GPS_IFD)

            lat = gps.get(2)  # GPSLatitude
            lat_ref = gps.get(1)  # GPSLatitudeRef
            lon = gps.get(4)  # GPSLongitude
            lon_ref = gps.get(3)  # GPSLongitudeRef

            if not all((lat, lat_ref, lon, lon_ref)):
                return None

            latitude = dms_to_decimal(lat, lat_ref)
            longitude = dms_to_decimal(lon, lon_ref)

            if not (-90 <= latitude <= 90):
                return None
            if not (-180 <= longitude <= 180):
                return None

            return latitude, longitude

    except (OSError, ValueError, TypeError, KeyError, ZeroDivisionError):
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Submit plaque photos with optional EXIF GPS detection."
    )
    parser.add_argument("title", help="Title of the plaque")
    parser.add_argument("files", nargs="+", type=Path, help="One or more local image files")
    parser.add_argument("--text", default="", help="Plaque inscription")
    parser.add_argument("--name", default="", help="Your name")
    parser.add_argument("--tags", default="", help="Comma-separated tags")
    parser.add_argument("--lat", type=float, help="Override EXIF latitude")
    parser.add_argument("--lon", type=float, help="Override EXIF longitude")
    args = parser.parse_args()

    paths = [p.expanduser().resolve() for p in args.files]

    for path in paths:
        if not path.is_file():
            parser.error(f"File does not exist: {path}")
        if path.stat().st_size > MAX_FILE_SIZE:
            parser.error(f"File exceeds 16 MB: {path}")

    # Find GPS coordinates in the first image that contains them.
    gps_coordinates = None
    gps_source = None

    for path in paths:
        coordinates = get_exif_gps(path)
        if coordinates is not None:
            gps_coordinates = coordinates
            gps_source = path
            break

    # Explicit command-line coordinates take precedence over EXIF.
    latitude = args.lat
    longitude = args.lon

    if latitude is None and gps_coordinates:
        latitude = gps_coordinates[0]
    if longitude is None and gps_coordinates:
        longitude = gps_coordinates[1]

    if latitude is not None and not -90 <= latitude <= 90:
        parser.error("Latitude must be between -90 and 90.")
    if longitude is not None and not -180 <= longitude <= 180:
        parser.error("Longitude must be between -180 and 180.")

    if gps_source:
        print(f"GPS coordinates found in: {gps_source.name}")
    else:
        print("No GPS coordinates found in image EXIF metadata.")

    print(f"Latitude:  {latitude if latitude is not None else 'not set'}")
    print(f"Longitude: {longitude if longitude is not None else 'not set'}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        try:
            page.goto(URL, wait_until="domcontentloaded")
            page.locator("#imageFile").set_input_files(
                [str(path) for path in paths]
            )

            page.get_by_label("Plaque Title").fill(args.title)

            if args.text:
                page.get_by_label("Plaque Text").fill(args.text)
            if args.name:
                page.get_by_label("Your Name").fill(args.name)
            if args.tags:
                page.get_by_label("Tags").fill(args.tags)

            if latitude is not None:
                page.get_by_label("Latitude").fill(str(latitude))
            if longitude is not None:
                page.get_by_label("Longitude").fill(str(longitude))

            print(f"\nPrepared {len(paths)} image(s).")
            print("Review the form and complete any CAPTCHA or required fields.")
            print("Click 'Submit A Plaque' when ready; close the browser when done.")

            page.wait_for_event("close", timeout=0)

        finally:
            browser.close()


if __name__ == "__main__":
    main()

