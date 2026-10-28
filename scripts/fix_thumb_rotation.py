#!/usr/bin/env python3
"""
fix_thumb_rotation.py — Regenerate thumbnails with EXIF orientation applied.

The original thumbnail generation may have ignored the EXIF orientation tag,
so some thumbnails appear rotated while the full-size image looks correct in
browsers (which apply EXIF automatically).

This script opens every full-size image, checks whether it carries an EXIF
orientation tag that requires rotation, and if so regenerates the thumbnail
with the correct orientation.

Usage (run from the project root):
    python scripts/fix_thumb_rotation.py            # dry run
    python scripts/fix_thumb_rotation.py --fix      # apply fixes
    python scripts/fix_thumb_rotation.py --fix -v   # verbose

On Fly.io:
    fly ssh console -C "cd /app && python scripts/fix_thumb_rotation.py --fix" \\
        -a readtheplaque-standalone
"""

import argparse
import io
import os
import sys

# Allow running from the project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageOps

from config import THUMB_DIR, THUMB_SIZE, UPLOAD_DIR
from database import get_db, init_db
from models import subdir_path


def needs_exif_correction(img: Image.Image) -> bool:
    """Return True if this image has an EXIF orientation tag that requires
    any rotation or flip (i.e. orientation != 1 / normal)."""
    try:
        exif = img._getexif()
        if exif:
            # Tag 0x0112 = Orientation
            orientation = exif.get(0x0112, 1)
            return orientation not in (1, None)
    except Exception:
        pass
    return False


def regenerate_thumb(image_file: str, thumb_file: str) -> bool:
    """Open the full-size image, apply EXIF orientation, save a new thumbnail.
    Returns True on success."""
    image_path = subdir_path(UPLOAD_DIR, image_file)
    thumb_path = subdir_path(THUMB_DIR, thumb_file)

    if not os.path.exists(image_path):
        return False

    try:
        with Image.open(image_path) as img:
            # exif_transpose rotates/flips the pixel data to match orientation
            # and strips the orientation tag so the result is always "normal"
            corrected = ImageOps.exif_transpose(img)
            # Cover-crop to thumbnail size, same as models._save_thumbnail
            thumb = ImageOps.fit(
                corrected.convert("RGB"), THUMB_SIZE, Image.LANCZOS
            )
            os.makedirs(os.path.dirname(thumb_path), exist_ok=True)
            thumb.save(thumb_path, "JPEG", quality=82, optimize=True)
        return True
    except Exception as e:
        print(f"    ERROR: {e}")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Fix thumbnail EXIF rotation.")
    parser.add_argument(
        "--fix", action="store_true", help="Apply fixes (default: dry run only)"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Print every file checked"
    )
    parser.add_argument(
        "--limit", type=int, default=0, help="Process at most N rows (0 = all)"
    )
    args = parser.parse_args()

    init_db()

    with get_db() as db:
        rows = db.execute(
            "SELECT id, plaque_id, image_file, thumb_file"
            " FROM plaque_images"
            " WHERE image_file IS NOT NULL AND thumb_file IS NOT NULL"
            " ORDER BY id"
        ).fetchall()

    if args.limit:
        rows = rows[: args.limit]

    total = len(rows)
    to_fix = 0
    fixed = 0
    errors = 0
    missing = 0

    print(f"Checking {total} image{'s' if total != 1 else ''}…\n")

    for row in rows:
        image_path = subdir_path(UPLOAD_DIR, row["image_file"])

        if not os.path.exists(image_path):
            missing += 1
            if args.verbose:
                print(f"  MISSING: {row['image_file']}")
            continue

        try:
            with Image.open(image_path) as img:
                needs_fix = needs_exif_correction(img)
        except Exception as e:
            print(f"  ERROR reading {row['image_file']}: {e}")
            errors += 1
            continue

        if not needs_fix:
            if args.verbose:
                print(f"  OK:  {row['image_file']}")
            continue

        to_fix += 1
        action = "FIX" if args.fix else "WOULD FIX"
        print(f"  {action}: {row['image_file']} → {row['thumb_file']}")

        if args.fix:
            if regenerate_thumb(row["image_file"], row["thumb_file"]):
                fixed += 1
                if args.verbose:
                    print(f"    → regenerated ✓")
            else:
                errors += 1

    print()
    if args.fix:
        print(
            f"Done.  Fixed: {fixed}  "
            f"Already correct: {total - to_fix - missing - errors}  "
            f"Missing source: {missing}  Errors: {errors}"
        )
    else:
        print(
            f"Dry run.  Would fix: {to_fix} of {total}  "
            f"Missing source: {missing}"
        )
        if to_fix:
            print("Run again with --fix to apply.")


if __name__ == "__main__":
    main()
