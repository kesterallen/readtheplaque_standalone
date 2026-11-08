"""Image upload helpers used by plaque submission workflows."""

import hashlib
import os

from flask import current_app, has_app_context
from markupsafe import escape

from config import ALLOWED_EXT, MAX_FILE_MB, THUMB_DIR, UPLOAD_DIR
from database import get_db
from models import make_thumbnail, new_image_filename, new_thumb_filename, subdir_path


def _setting(name: str, default):
    return current_app.config.get(name, default) if has_app_context() else default


def save_images(image_files: list) -> tuple[list[dict], list[str]]:
    """Validate, de-duplicate, and persist uploaded images.

    Returns metadata for files written to disk and user-facing validation errors.
    The caller must call cleanup_saved_images if the submission is rejected.
    """
    saved_images: list[dict] = []
    errors: list[str] = []
    allowed_ext = _setting("ALLOWED_EXT", ALLOWED_EXT)
    max_file_mb = _setting("MAX_FILE_MB", MAX_FILE_MB)
    upload_dir = _setting("UPLOAD_FOLDER", UPLOAD_DIR)
    thumb_dir = _setting("THUMB_FOLDER", THUMB_DIR)

    image_files = [file for file in image_files if file and file.filename]
    if not image_files:
        return saved_images, ["At least one image is required."]

    for image_file in image_files:
        ext = image_file.filename.rsplit(".", 1)[-1].lower()
        if ext not in allowed_ext:
            errors.append(
                f"'{escape(image_file.filename)}': allowed types are "
                f"{', '.join(sorted(allowed_ext))}"
            )

        image_file.stream.seek(0, os.SEEK_END)
        size = image_file.stream.tell()
        image_file.stream.seek(0)
        if size > max_file_mb * 1024 * 1024:
            errors.append(
                f"'{escape(image_file.filename)}' is {size / 1048576:.1f} MB; "
                f"the limit is {max_file_mb} MB per photo."
            )

    if errors:
        return saved_images, errors

    for image_file in image_files:
        ext = image_file.filename.rsplit(".", 1)[-1].lower()
        data = image_file.read()
        image_hash = hashlib.sha256(data).hexdigest()

        with get_db() as db:
            duplicate = db.execute(
                "SELECT p.title AS title, p.slug AS slug "
                "FROM plaque_images pi "
                "JOIN plaques p ON pi.plaque_id = p.id "
                "WHERE pi.image_hash=?",
                (image_hash,),
            ).fetchone()

        if duplicate:
            errors.append(
                f"Image {escape(image_file.filename)} is a duplicate of "
                f'<a href="/plaque/{escape(duplicate["slug"])}">'
                f'{escape(duplicate["title"])}</a>.'
            )
            continue

        filename = new_image_filename(ext)
        with open(subdir_path(upload_dir, filename), "wb") as image_handle:
            image_handle.write(data)

        thumb_filename = new_thumb_filename()
        thumb_ok = make_thumbnail(filename, thumb_filename)
        saved_images.append(
            {
                "filename": filename,
                "thumb": thumb_filename if thumb_ok else None,
                "hash": image_hash,
                "original_name": image_file.filename,
            }
        )

    return saved_images, errors


def cleanup_saved_images(saved_images: list[dict]) -> None:
    """Remove upload and thumbnail files when a submission cannot be saved."""
    upload_dir = _setting("UPLOAD_FOLDER", UPLOAD_DIR)
    thumb_dir = _setting("THUMB_FOLDER", THUMB_DIR)
    for saved_image in saved_images:
        paths = [(upload_dir, saved_image.get("filename"))]
        if saved_image.get("thumb"):
            paths.append((thumb_dir, saved_image["thumb"]))

        for directory, filename in paths:
            if not filename:
                continue
            try:
                os.remove(subdir_path(directory, filename))
            except OSError:
                pass
