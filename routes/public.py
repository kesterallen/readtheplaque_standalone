"""Public-facing routes: homepage, plaque detail, map, submit, tag, random, about."""

import random
import re

from flask import (
    Blueprint,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)

from config import ALLOWED_EXT, THUMB_DIR, UPLOAD_DIR
from database import get_db
from models import (
    _placeholder_jpeg,
    add_image_to_plaque,
    get_images_for_plaque,
    get_tags_for_plaque,
    image_url,
    make_thumbnail,
    new_image_filename,
    new_thumb_filename,
    parse_tags,
    plaque_to_dict,
    sanitise_description,
    set_tags_for_plaque,
    subdir_path,
    thumb_url,
)

import hashlib
import os

public_bp = Blueprint("public", __name__)


# ── Homepage ───────────────────────────────────────────────────────────────────
@public_bp.route("/")
@public_bp.route("/page/<int:page>")
def index(page=1):
    per_page = 12
    page = max(1, page)
    offset = (page - 1) * per_page

    with get_db() as db:
        total = db.execute("SELECT COUNT(*) FROM plaques WHERE approved=1").fetchone()[
            0
        ]

        featured_row = db.execute(
            "SELECT * FROM plaques WHERE approved=1 AND is_featured=1 LIMIT 1"
        ).fetchone()
        if not featured_row:
            featured_row = db.execute(
                "SELECT * FROM plaques WHERE approved=1 ORDER BY created_at DESC LIMIT 1"
            ).fetchone()

        featured_id = featured_row["id"] if featured_row else None

        rows = db.execute(
            "SELECT * FROM plaques WHERE approved=1 AND id != ?"
            " ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (featured_id or -1, per_page, offset),
        ).fetchall()

    featured = plaque_to_dict(featured_row) if (page == 1 and featured_row) else None
    recent = [plaque_to_dict(r) for r in rows]
    total_pages = max(1, -(-total // per_page))

    return render_template(
        "index.html",
        featured=featured,
        recent=recent,
        total=total,
        page=page,
        total_pages=total_pages,
    )


# ── Map ────────────────────────────────────────────────────────────────────────
@public_bp.route("/map")
@public_bp.route("/map/<path:coords>")
def map_view(coords=None):
    lat, lng, zoom = 20.0, 10.0, 2
    if coords:
        parts = coords.split("/")
        if len(parts) == 3:
            try:
                lat = max(-90.0, min(90.0, float(parts[0])))
                lng = max(-180.0, min(180.0, float(parts[1])))
                zoom = max(1, min(19, int(parts[2])))
            except ValueError:
                pass
    with get_db() as db:
        total = db.execute("SELECT COUNT(*) FROM plaques WHERE approved=1").fetchone()[
            0
        ]
    return render_template(
        "map.html", total=total, init_lat=lat, init_lng=lng, init_zoom=zoom
    )


# ── Submit ─────────────────────────────────────────────────────────────────────
@public_bp.route("/submit", methods=["GET", "POST"])
def submit():
    if request.method == "GET":
        return render_template("submit.html")

    errors = []
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    submitted_by = request.form.get("submitted_by", "anonymous").strip() or "anonymous"
    raw_tags = request.form.get("tags", "")
    tag_names = parse_tags(raw_tags)

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

    image_files = request.files.getlist("images")
    saved_images, img_errors = _save_images(image_files)
    errors.extend(img_errors)

    if not saved_images:
        return jsonify({"ok": False, "errors": ["No images could be saved."]}), 400
    if errors:
        return jsonify({"ok": False, "errors": errors}), 400

    # If created_at or updated_at exist in the form, use them and submit them
    created_at = request.form.get("created_at", None)
    updated_at = request.form.get("updated_at", None)

    plaque_id, slug, duplicates = _insert_plaque_rows(
        title, description, lat, lng, submitted_by, created_at, updated_at, saved_images
    )
    with get_db() as db:
        set_tags_for_plaque(db, plaque_id, tag_names)

    resp = {"ok": True, "slug": slug, "pending": True}
    if duplicates:
        resp["duplicates"] = duplicates
    return jsonify(resp)


def _make_slug(title: str, slug_from_form: str = None) -> str:
    base_slug = request.form.get("slug", slug_from_form)
    if base_slug is None:
        base_slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    slug = base_slug
    suffix = 1
    same_slug_sql = "SELECT COUNT(*) FROM plaques WHERE slug=?"
    with get_db() as db:
        while (count := db.execute(same_slug_sql, (slug,)).fetchone()[0]) != 0:
            suffix += 1
            slug = f"{base_slug}{suffix}"
    return slug


def _save_images(image_files: list) -> tuple[list[dict], list[str]]:
    saved_images: list[dict] = []
    errors: list[str] = []

    image_files = [f for f in image_files if f and f.filename]
    if not image_files:
        errors.append("At least one image is required.")
        return saved_images, errors

    for f in image_files:
        ext = f.filename.rsplit(".", 1)[-1].lower()
        if ext not in ALLOWED_EXT:
            errors.append(f"'{f.filename}': allowed types are {', '.join(ALLOWED_EXT)}")

    if errors:
        return saved_images, errors

    for image_file in image_files:
        ext = image_file.filename.rsplit(".", 1)[-1].lower()
        data = image_file.read()
        image_hash = hashlib.sha256(data).hexdigest()
        filename = new_image_filename(ext)
        with open(subdir_path(UPLOAD_DIR, filename), "wb") as fh:
            fh.write(data)
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
) -> tuple[int, str, list[str]]:
    with get_db() as db:
        primary = saved_images[0]
        slug = _make_slug(title, request.form.get("slug"))

        # Build column list and values dynamically for optional fields
        cols = ["slug", "title", "description", "latitude", "longitude",
                "image_file", "thumb_file", "submitted_by", "approved"]
        vals = [slug, title, description, lat, lng,
                primary["filename"], primary["thumb"], submitted_by, 0]
        if created_at is not None:
            cols.append("created_at")
            vals.append(created_at)
        if updated_at is not None:
            cols.append("updated_at")
            vals.append(updated_at)

        placeholders = ", ".join("?" * len(cols))

        db.execute( f"INSERT INTO plaques ({', '.join(cols)}) VALUES ({placeholders})", vals)
        plaque_id = db.execute( "SELECT id FROM plaques WHERE slug=?", (slug,)).fetchone()["id"]

        saved = 0
        duplicates: list[str] = []
        for i, img in enumerate(saved_images):
            db.execute(
                "INSERT INTO plaque_images"
                " (plaque_id, image_file, thumb_file, image_hash, is_primary, sort_order)"
                " VALUES (?,?,?,?,?,?)",
                (
                    plaque_id,
                    img["filename"],
                    img["thumb"],
                    img["hash"],
                    1 if saved == 0 else 0,
                    i,
                ),
            )
            saved += 1

    return plaque_id, slug, duplicates


# ── Plaque detail ──────────────────────────────────────────────────────────────
@public_bp.route("/plaque/<slug>")
def plaque_detail(slug):
    with get_db() as db:
        row = db.execute(
            "SELECT * FROM plaques WHERE slug=? AND approved=1", (slug,)
        ).fetchone()
        if not row:
            abort(404)
        tags = get_tags_for_plaque(db, row["id"])
        images = get_images_for_plaque(db, row["id"])

    plaque = plaque_to_dict(row)
    plaque["tags"] = tags
    plaque["images"] = [
        {
            "image_url": image_url(img["image_file"]),
            "thumb_url": thumb_url(img["thumb_file"]) or image_url(img["image_file"]),
            "id": img["id"],
            "is_primary": img["is_primary"],
        }
        for img in images
    ]
    plaque["description_html"] = (
        sanitise_description(plaque["description"]) if plaque.get("description") else ""
    )
    return render_template("detail.html", plaque=plaque)


# ── Tag page ───────────────────────────────────────────────────────────────────
@public_bp.route("/tag/<tag_name>")
def tag_page(tag_name):
    tag_name = tag_name.strip().lower()
    with get_db() as db:
        tag = db.execute("SELECT * FROM tags WHERE name=?", (tag_name,)).fetchone()
        if not tag:
            abort(404)
        rows = db.execute(
            "SELECT p.* FROM plaques p"
            " JOIN plaque_tags pt ON pt.plaque_id = p.id"
            " JOIN tags t ON t.id = pt.tag_id"
            " WHERE t.name=? AND p.approved=1 ORDER BY p.created_at DESC",
            (tag_name,),
        ).fetchall()
    plaques = [plaque_to_dict(r) for r in rows]
    return render_template("tag.html", tag=tag_name, plaques=plaques)


# ── Random & About ─────────────────────────────────────────────────────────────
@public_bp.route("/random")
def random_plaque():
    with get_db() as db:
        rows = db.execute("SELECT slug FROM plaques WHERE approved=1").fetchall()
    if not rows:
        abort(404)
    slug = random.choice(rows)["slug"]
    return redirect(url_for("public.plaque_detail", slug=slug))


@public_bp.route("/about")
def about():
    return render_template("about.html")


# ── File serving ───────────────────────────────────────────────────────────────
@public_bp.route("/uploads/<path:filename>")
def uploaded_file(filename):
    fp = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(fp):
        return _placeholder_jpeg(filename), 200, {"Content-Type": "image/jpeg"}
    return send_from_directory(UPLOAD_DIR, filename)


@public_bp.route("/thumbs/<path:filename>")
def thumb_file(filename):
    fp = os.path.join(THUMB_DIR, filename)
    if not os.path.exists(fp):
        return _placeholder_jpeg(filename), 200, {"Content-Type": "image/jpeg"}
    return send_from_directory(THUMB_DIR, filename)
