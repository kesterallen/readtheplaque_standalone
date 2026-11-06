"""Plaque submission endpoint and image persistence helpers."""

import hashlib
import os

from flask import jsonify, render_template, request, session
from markupsafe import escape

from config import (
    ALLOWED_EXT,
    HCAPTCHA_SITEKEY,
    MAX_FILE_MB,
    MAX_UPLOAD_MB,
    UPLOAD_DIR,
)
from database import get_db
from models import (
    make_or_update_slug,
    make_thumbnail,
    new_image_filename,
    new_thumb_filename,
    parse_tags,
    set_tags_for_plaque,
    subdir_path,
)
from spam import (
    HONEYPOT_FIELD,
    check_content,
    check_honeypot,
    check_rate_limit,
    verify_captcha,
)


def submit():
    if request.method == "GET":
        return render_template(
            "submit.html",
            hcaptcha_sitekey=HCAPTCHA_SITEKEY,
            honeypot_field=HONEYPOT_FIELD,
            max_file_mb=MAX_FILE_MB,
            max_upload_mb=MAX_UPLOAD_MB,
        )

    if check_honeypot(request.form):
        return jsonify({"ok": True, "slug": "pending", "pending": True})

    ip = (
        request.headers.get("X-Forwarded-For", request.remote_addr or "")
        .split(",")[0]
        .strip()
    )
    rate_ok, rate_err = check_rate_limit(ip)
    if not rate_ok:
        return jsonify({"ok": False, "errors": [rate_err]}), 429

    captcha_ok, captcha_err = verify_captcha(request.form.get("h-captcha-response", ""))
    if not captcha_ok:
        return jsonify({"ok": False, "errors": [captcha_err]}), 400

    errors = []
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    submitted_by = request.form.get("submitted_by", "anonymous").strip() or "anonymous"
    tag_names = parse_tags(request.form.get("tags", ""))

    try:
        lat = float(request.form.get("latitude", ""))
        lng = float(request.form.get("longitude", ""))
    except ValueError:
        errors.append("Valid latitude and longitude are required.")
        lat = lng = 0.0

    if not title:
        errors.append("Title is required.")
    if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
        errors.append("Coordinates out of range.")

    content_ok, content_err = check_content(title, description)
    if not content_ok:
        errors.append(content_err)

    saved_images, image_errors = _save_images(request.files.getlist("images"))
    errors.extend(image_errors)
    if not saved_images:
        return jsonify({"ok": False, "errors": errors or ["No images could be saved."]}), 400
    if errors:
        return jsonify({"ok": False, "errors": errors}), 400

    if session.get("admin") is True:
        created_at = request.form.get("created_at")
        updated_at = request.form.get("updated_at")
    else:
        created_at = updated_at = None

    plaque_id, slug = _insert_plaque_rows(
        title, description, lat, lng, submitted_by, created_at, updated_at, saved_images
    )
    with get_db() as db:
        set_tags_for_plaque(db, plaque_id, tag_names)

    return jsonify({"ok": True, "slug": slug, "pending": True, "lat": lat, "lng": lng})


def _save_images(image_files: list) -> tuple[list[dict], list[str]]:
    saved_images = []
    errors = []
    image_files = [file for file in image_files if file and file.filename]
    if not image_files:
        return saved_images, ["At least one image is required."]

    for file in image_files:
        ext = file.filename.rsplit(".", 1)[-1].lower()
        if ext not in ALLOWED_EXT:
            errors.append(
                f"'{escape(file.filename)}': allowed types are {', '.join(ALLOWED_EXT)}"
            )
        file.stream.seek(0, os.SEEK_END)
        size = file.stream.tell()
        file.stream.seek(0)
        if size > MAX_FILE_MB * 1024 * 1024:
            errors.append(
                f"'{escape(file.filename)}' is {size / 1048576:.1f} MB; "
                f"the limit is {MAX_FILE_MB} MB per photo."
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
                "FROM plaque_images pi JOIN plaques p ON pi.plaque_id=p.id "
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
        with open(subdir_path(UPLOAD_DIR, filename), "wb") as image_handle:
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


def _insert_plaque_rows(
    title, description, lat, lng, submitted_by, created_at, updated_at, saved_images
) -> tuple[int, str]:
    with get_db() as db:
        primary = saved_images[0]
        slug = make_or_update_slug(db, title)
        columns = [
            "slug", "title", "description", "latitude", "longitude",
            "image_file", "thumb_file", "submitted_by", "approved",
        ]
        values = [
            slug, title, description, lat, lng, primary["filename"],
            primary["thumb"], submitted_by, 0,
        ]
        if created_at is not None:
            columns.append("created_at")
            values.append(created_at)
        if updated_at is not None:
            columns.append("updated_at")
            values.append(updated_at)

        placeholders = ", ".join("?" * len(columns))
        db.execute(
            f"INSERT INTO plaques ({', '.join(columns)}) VALUES ({placeholders})",
            values,
        )
        plaque_id = db.execute(
            "SELECT id FROM plaques WHERE slug=?", (slug,)
        ).fetchone()["id"]
        for index, image in enumerate(saved_images):
            db.execute(
                "INSERT INTO plaque_images"
                " (plaque_id, image_file, thumb_file, image_hash, is_primary, sort_order)"
                " VALUES (?,?,?,?,?,?)",
                (
                    plaque_id,
                    image["filename"],
                    image["thumb"],
                    image["hash"],
                    int(index == 0),
                    index,
                ),
            )
    return plaque_id, slug


def register_submission_routes(public_blueprint):
    """Attach submission handling to the public blueprint with its legacy endpoint."""
    public_blueprint.add_url_rule(
        "/submit", endpoint="submit", view_func=submit, methods=["GET", "POST"]
    )
