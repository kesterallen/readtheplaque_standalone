"""Admin routes: login, queue, plaques list, edit, approve, reject, rotate, feature, images."""

import datetime
import io
import os
import random

from flask import (
    Blueprint,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from PIL import Image

from config import ADMIN_PASSWORD, ALLOWED_EXT, PER_PAGE, THUMB_DIR, UPLOAD_DIR
from database import get_db
from models import (
    add_image_to_plaque,
    get_images_for_plaque,
    get_tags_for_plaque,
    image_url,
    make_thumbnail,
    new_image_filename,
    new_thumb_filename,
    parse_tags,
    plaque_to_dict,
    set_tags_for_plaque,
    subdir_path,
    sync_primary_image,
    thumb_url,
)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def is_admin() -> bool:
    return session.get("admin") is True


# ── Auth ───────────────────────────────────────────────────────────────────────
@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form.get("password") == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(url_for("admin.queue"))
        error = "Incorrect password."
    return render_template("admin_login.html", error=error)


@admin_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("public.index"))


# ── Queue ──────────────────────────────────────────────────────────────────────
@admin_bp.route("/queue")
def queue():
    if not is_admin():
        return redirect(url_for("admin.login"))
    page = max(1, request.args.get("page", 1, type=int))
    offset = (page - 1) * PER_PAGE
    with get_db() as db:
        total = db.execute("SELECT COUNT(*) FROM plaques WHERE approved=0").fetchone()[
            0
        ]
        pending = db.execute(
            "SELECT * FROM plaques WHERE approved=0 ORDER BY created_at ASC"
            " LIMIT ? OFFSET ?",
            (PER_PAGE, offset),
        ).fetchall()
    total_pages = max(1, -(-total // PER_PAGE))
    return render_template(
        "admin_queue.html",
        pending=[plaque_to_dict(p) for p in pending],
        total=total,
        page=page,
        total_pages=total_pages,
    )


# ── Plaques list ───────────────────────────────────────────────────────────────
@admin_bp.route("/plaques")
def plaques():
    if not is_admin():
        return redirect(url_for("admin.login"))

    page = max(1, request.args.get("page", 1, type=int))
    per_page = 24
    offset = (page - 1) * per_page

    status = request.args.get("status", "all")

    where_clauses: list[str] = []
    params: list = []

    if status == "approved":
        where_clauses.append("approved = 1")
    elif status == "pending":
        where_clauses.append("approved = 0")

    q = request.args.get("q", "").strip()
    if q:
        where_clauses.append("title LIKE ?")
        params.append(f"%{q}%")

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    sort_col = request.args.get("sort", "created_at")
    sort_dir = request.args.get("dir", "desc")

    allowed_cols = {"title", "created_at", "updated_at", "submitted_by", "approved"}
    if sort_col not in allowed_cols:
        sort_col = "created_at"
    if sort_dir not in ("asc", "desc"):
        sort_dir = "desc"

    order_sql = f"ORDER BY {sort_col} {sort_dir.upper()}"

    with get_db() as db:
        rows = db.execute(
            f"SELECT * FROM plaques {where_sql} {order_sql} LIMIT ? OFFSET ?",
            (*params, per_page, offset),
        ).fetchall()
        total = db.execute(f"SELECT COUNT(*) FROM plaques {where_sql}", params).fetchone()[0]

    total_pages = max(1, -(-total // per_page))
    return render_template(
        "admin_plaques.html",
        plaques=[plaque_to_dict(r) for r in rows],
        page=page,
        total_pages=total_pages,
        total=total,
        status=status,
        q=q,
        sort=sort_col,
        dir=sort_dir,
    )


# ── Approve / reject ───────────────────────────────────────────────────────────
@admin_bp.route("/approve/all", methods=["GET", "POST"])
def approve_all():
    # TODO: remove this endpoint
    with get_db() as db:
        db.execute("UPDATE plaques SET approved=1")
    return jsonify({"ok": True})


@admin_bp.route("/approve/<int:plaque_id>", methods=["POST"])
def approve(plaque_id):
    if not is_admin():
        return jsonify({"ok": False, "error": "Not authenticated"}), 403
    with get_db() as db:
        db.execute("UPDATE plaques SET approved=1 WHERE id=?", (plaque_id,))
    return jsonify({"ok": True})


@admin_bp.route("/reject/<int:plaque_id>", methods=["POST"])
def reject(plaque_id):
    if not is_admin():
        return jsonify({"ok": False, "error": "Not authenticated"}), 403
    with get_db() as db:
        row = db.execute(
            "SELECT image_file, thumb_file FROM plaques WHERE id=?", (plaque_id,)
        ).fetchone()
        if row:
            for col, folder in [("image_file", UPLOAD_DIR), ("thumb_file", THUMB_DIR)]:
                f = row[col]
                if f:
                    try:
                        os.remove(subdir_path(folder, f))
                    except OSError:
                        pass
            db.execute("DELETE FROM plaques WHERE id=?", (plaque_id,))
    return jsonify({"ok": True})


# ── Edit ───────────────────────────────────────────────────────────────────────
@admin_bp.route("/edit/<int:plaque_id>", methods=["GET", "POST"])
def edit(plaque_id):
    if not is_admin():
        return redirect(url_for("admin.login"))

    with get_db() as db:
        row = db.execute("SELECT * FROM plaques WHERE id=?", (plaque_id,)).fetchone()
    if not row:
        abort(404)

    if request.method == "GET":
        with get_db() as db:
            tags = get_tags_for_plaque(db, plaque_id)
            images = get_images_for_plaque(db, plaque_id)
        plaque = plaque_to_dict(row)
        plaque["tags"] = tags
        plaque["images"] = [
            {
                "image_url": image_url(img["image_file"]),
                "thumb_url": thumb_url(img["thumb_file"])
                or image_url(img["image_file"]),
                "id": img["id"],
                "is_primary": img["is_primary"],
                "sort_order": img["sort_order"],
            }
            for img in images
        ]
        return render_template("admin_edit.html", plaque=plaque)

    # POST — save edits
    errors = []
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    submitted_by = request.form.get("submitted_by", "").strip()
    approved = 1 if request.form.get("approved") else 0

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

    new_image = request.files.get("image")
    new_img_file = row["image_file"]
    new_thumb_file = row["thumb_file"]

    if new_image and new_image.filename:
        ext = new_image.filename.rsplit(".", 1)[-1].lower()
        if ext not in ALLOWED_EXT:
            errors.append(f"Allowed image types: {', '.join(ALLOWED_EXT)}")
        else:
            filename = new_image_filename(ext)
            new_image.save(subdir_path(UPLOAD_DIR, filename))
            thumb_filename = new_thumb_filename()
            thumb_ok = make_thumbnail(filename, thumb_filename)
            for old_f, folder in [
                (row["image_file"], UPLOAD_DIR),
                (row["thumb_file"], THUMB_DIR),
            ]:
                if old_f:
                    try:
                        os.remove(subdir_path(folder, old_f))
                    except OSError:
                        pass
            new_img_file = filename
            new_thumb_file = thumb_filename if thumb_ok else None

    if errors:
        return render_template(
            "admin_edit.html", plaque=plaque_to_dict(row), errors=errors
        )

    set_featured = bool(request.form.get("set_featured"))
    tag_names = parse_tags(request.form.get("tags", ""))

    with get_db() as db:
        set_tags_for_plaque(db, plaque_id, tag_names)
        if set_featured:
            db.execute("UPDATE plaques SET is_featured=0")
        db.execute(
            "UPDATE plaques SET title=?, description=?, latitude=?, longitude=?,"
            " submitted_by=?, approved=?, is_featured=?, image_file=?, thumb_file=?,"
            " updated_at=? WHERE id=?",
            (
                title,
                description,
                lat,
                lng,
                submitted_by,
                approved,
                1 if set_featured else 0,
                new_img_file,
                new_thumb_file,
                datetime.datetime.now(datetime.UTC),
                plaque_id,
            ),
        )

    return redirect(url_for("admin.queue"))


# ── Rotate ─────────────────────────────────────────────────────────────────────
@admin_bp.route("/rotate/<int:plaque_id>", methods=["POST"])
def rotate(plaque_id):
    """Rotate 90° clockwise. ?type=image treats plaque_id as plaque_images.id."""
    if not is_admin():
        return jsonify({"ok": False, "error": "Not authenticated"}), 403

    use_image_id = request.args.get("type") == "image"
    with get_db() as db:
        if use_image_id:
            row = db.execute(
                "SELECT image_file, thumb_file FROM plaque_images WHERE id=?",
                (plaque_id,),
            ).fetchone()
        else:
            row = db.execute(
                "SELECT image_file, thumb_file FROM plaques WHERE id=?", (plaque_id,)
            ).fetchone()
    if not row:
        return jsonify({"ok": False, "error": "Not found"}), 404

    img_path = subdir_path(UPLOAD_DIR, row["image_file"])
    if not os.path.exists(img_path):
        return jsonify({"ok": False, "error": "Image file not found"}), 404

    try:
        with Image.open(img_path) as img:
            img.rotate(-90, expand=True).save(img_path)
        if row["thumb_file"]:
            make_thumbnail(row["image_file"], row["thumb_file"])
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

    return jsonify({"ok": True})


# ── Feature ────────────────────────────────────────────────────────────────────
@admin_bp.route("/feature/<int:plaque_id>", methods=["POST"])
def feature(plaque_id):
    if not is_admin():
        return jsonify({"ok": False, "error": "Not authenticated"}), 403
    with get_db() as db:
        row = db.execute(
            "SELECT id FROM plaques WHERE id=? AND approved=1", (plaque_id,)
        ).fetchone()
        if not row:
            return (
                jsonify({"ok": False, "error": "Plaque not found or not approved"}),
                404,
            )
        with db:
            db.execute("UPDATE plaques SET is_featured=0")
            db.execute("UPDATE plaques SET is_featured=1 WHERE id=?", (plaque_id,))
    return jsonify({"ok": True, "featured_id": plaque_id})


# ── Image management ───────────────────────────────────────────────────────────
@admin_bp.route("/images/<int:plaque_id>/add", methods=["POST"])
def image_add(plaque_id):
    if not is_admin():
        return jsonify({"ok": False, "error": "Not authenticated"}), 403
    f = request.files.get("image")
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "No image provided"}), 400
    ext = f.filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXT:
        return jsonify({"ok": False, "error": "File type not allowed"}), 400
    with get_db() as db:
        count = db.execute(
            "SELECT COUNT(*) FROM plaque_images WHERE plaque_id=?", (plaque_id,)
        ).fetchone()[0]
        result = add_image_to_plaque(
            db, plaque_id, f, ext, is_primary=(count == 0), sort_order=count
        )
        if result["duplicate"]:
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "Duplicate image — already attached to this plaque",
                        "duplicate": True,
                    }
                ),
                409,
            )
        row = db.execute(
            "SELECT id FROM plaque_images WHERE plaque_id=? ORDER BY id DESC LIMIT 1",
            (plaque_id,),
        ).fetchone()
    return jsonify(
        {
            "ok": True,
            "id": row["id"],
            "image_url": image_url(result["image_file"]),
            "thumb_url": thumb_url(result["thumb_file"])
            or image_url(result["image_file"]),
        }
    )


@admin_bp.route("/images/<int:image_id>/delete", methods=["POST"])
def image_delete(image_id):
    if not is_admin():
        return jsonify({"ok": False, "error": "Not authenticated"}), 403
    with get_db() as db:
        img = db.execute(
            "SELECT * FROM plaque_images WHERE id=?", (image_id,)
        ).fetchone()
        if not img:
            return jsonify({"ok": False, "error": "Image not found"}), 404
        plaque_id = img["plaque_id"]
        count = db.execute(
            "SELECT COUNT(*) FROM plaque_images WHERE plaque_id=?", (plaque_id,)
        ).fetchone()[0]
        if count <= 1:
            return jsonify({"ok": False, "error": "Cannot delete the only image"}), 400
        for f, folder in [
            (img["image_file"], UPLOAD_DIR),
            (img["thumb_file"], THUMB_DIR),
        ]:
            if f:
                try:
                    os.remove(subdir_path(folder, f))
                except OSError:
                    pass
        db.execute("DELETE FROM plaque_images WHERE id=?", (image_id,))
        if img["is_primary"]:
            db.execute(
                "UPDATE plaque_images SET is_primary=1"
                " WHERE plaque_id=? ORDER BY sort_order, id LIMIT 1",
                (plaque_id,),
            )
            sync_primary_image(db, plaque_id)
    return jsonify({"ok": True})


@admin_bp.route("/images/<int:image_id>/set-primary", methods=["POST"])
def image_set_primary(image_id):
    if not is_admin():
        return jsonify({"ok": False, "error": "Not authenticated"}), 403
    with get_db() as db:
        img = db.execute(
            "SELECT * FROM plaque_images WHERE id=?", (image_id,)
        ).fetchone()
        if not img:
            return jsonify({"ok": False, "error": "Image not found"}), 404
        plaque_id = img["plaque_id"]
        db.execute(
            "UPDATE plaque_images SET is_primary=0 WHERE plaque_id=?", (plaque_id,)
        )
        db.execute("UPDATE plaque_images SET is_primary=1 WHERE id=?", (image_id,))
        sync_primary_image(db, plaque_id)
    return jsonify({"ok": True})
