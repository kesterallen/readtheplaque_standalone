"""Public-facing page routes: browsing, plaque details, maps, and filters."""

import os
import random
from urllib.parse import quote

from flask import (
    Blueprint,
    abort,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from markupsafe import Markup

from config import (
    PER_PAGE,
    SHARE_IMAGE_MAX_MB,
    SITE_URL,
    THUMB_DIR,
    UPLOAD_DIR,
)
from database import get_db
from models import (
    _placeholder_jpeg,
    get_images_for_plaque,
    get_tags_for_plaque,
    image_url,
    path_to_lat_lng_zoom,
    plaque_to_dict,
    sanitise_description,
    subdir_path,
    thumb_url,
)
from routes.api import _get_closest_plaques
from routes.submissions import register_submission_routes

public_bp = Blueprint("public", __name__)


@public_bp.route("/")
@public_bp.route("/page/<int:page>")
def index(page=1):
    page = max(1, request.args.get("page", page, type=int))
    offset = (page - 1) * PER_PAGE

    with get_db() as db:
        total = db.execute("SELECT COUNT(*) FROM plaques WHERE approved=1").fetchone()[0]
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
            (featured_id or -1, PER_PAGE, offset),
        ).fetchall()

    return render_template(
        "index.html",
        featured=plaque_to_dict(featured_row) if featured_row else None,
        recent=[plaque_to_dict(row) for row in rows],
        total=total,
        page=page,
        total_pages=max(1, -(-total // PER_PAGE)),
    )


@public_bp.route("/rss")
@public_bp.route("/feed")
def feed():
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM plaques WHERE approved=1 ORDER BY created_at DESC LIMIT ?",
            (PER_PAGE,),
        ).fetchall()
    return render_template("feed.xml", recent=[plaque_to_dict(row) for row in rows])


@public_bp.route("/map")
@public_bp.route("/map/<path:coords>")
def map_view(coords=None):
    lat, lng, zoom = 30.0, -160.0, 2
    if coords:
        lat, lng, zoom = path_to_lat_lng_zoom(coords, lat, lng, zoom)
    with get_db() as db:
        total = db.execute("SELECT COUNT(*) FROM plaques WHERE approved=1").fetchone()[0]
    return render_template(
        "map.html", total=total, init_lat=lat, init_lng=lng, init_zoom=zoom
    )


def _site_root() -> str:
    """Return the configured site URL or the current request's external origin."""
    if SITE_URL:
        return SITE_URL
    scheme = request.headers.get("X-Forwarded-Proto", request.scheme).split(",")[0].strip()
    if scheme not in ("http", "https"):
        scheme = request.scheme
    return f"{scheme}://{request.host}"


def _share_description(raw: str | None, limit: int = 200) -> str:
    """Create a plain-text summary for social sharing metadata."""
    text = Markup(raw or "").striptags()
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0].rstrip(" ,.;:-–—") + "…"
    return text or "A plaque on Read The Plaque, a map of the world's historical plaques."


def _share_image(plaque: dict) -> tuple[str, str]:
    """Choose a full-size or thumbnail image for link previews."""
    try:
        size = os.path.getsize(subdir_path(UPLOAD_DIR, plaque["image_file"]))
    except OSError:
        size = None
    if size is not None and size <= SHARE_IMAGE_MAX_MB * 1024 * 1024:
        return _site_root() + plaque["image_url"], "summary_large_image"
    return _site_root() + plaque["thumb_url"], "summary"


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
    image, card = _share_image(plaque)
    share = {
        "url": _site_root() + url_for("public.plaque_detail", slug=plaque["slug"]),
        "description": _share_description(plaque.get("description")),
        "image": image,
        "card": card,
    }
    return render_template(
        "detail.html", plaque=plaque, share=share, is_admin=session.get("admin", False)
    )


@public_bp.route("/search")
@public_bp.route("/search/<int:page>")
def search_page(page=1):
    page = max(1, request.args.get("page", page, type=int))
    offset = (page - 1) * PER_PAGE
    q = request.args.get("q", "").strip()
    if not q:
        return redirect(url_for("public.index"))

    like = f"%{q}%"
    with get_db() as db:
        total = db.execute(
            "SELECT COUNT(*) FROM plaques WHERE approved=1"
            " AND (title LIKE ? OR description LIKE ?)",
            (like, like),
        ).fetchone()[0]
        rows = db.execute(
            "SELECT * FROM plaques WHERE approved=1"
            " AND (title LIKE ? OR description LIKE ?)"
            " ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (like, like, PER_PAGE, offset),
        ).fetchall()

    return render_template(
        "search_results.html",
        mode="search",
        page_title=f"Search: {q} — Read The Plaque",
        paginator_url=f"/search?q={q}",
        map_id="search-map",
        list_heading="Results",
        q=q,
        plaques=[plaque_to_dict(row) for row in rows],
        total=total,
        page=page,
        total_pages=max(1, -(-total // PER_PAGE)),
    )


@public_bp.route("/random_group")
def random_group():
    """Show a fresh selection of up to 24 random approved plaques."""
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM plaques WHERE approved=1 ORDER BY RANDOM() LIMIT 24"
        ).fetchall()
    plaques = [plaque_to_dict(row) for row in rows]
    return render_template(
        "listing.html",
        mode="random_group",
        page_title="A Random Group of Plaques — Read The Plaque",
        map_id="random-group-map",
        list_heading="Random plaques",
        plaques=plaques,
        total=len(plaques),
        page=1,
        total_pages=1,
        paginator_url=None,
    )


@public_bp.route("/nearby/<lat>/<lng>")
def nearby_gallery(lat, lng):
    """Show approved plaques nearest to a coordinate pair."""
    try:
        lat_f, lng_f = float(lat), float(lng)
    except ValueError:
        abort(404)
    if not (-90 <= lat_f <= 90 and -180 <= lng_f <= 180):
        abort(404)

    plaques = _get_closest_plaques(lat_f, lng_f, limit=PER_PAGE)
    for plaque in plaques:
        km = plaque.get("distance_km") or 0.0
        plaque["distance_km"] = round(km, 1)
        plaque["distance_mi"] = round(km / 1.609344, 1)
    return render_template(
        "listing.html",
        mode="nearby",
        page_title="Plaques near you — Read The Plaque",
        paginator_url=None,
        map_id="nearby-map",
        list_heading="Nearest first",
        lat=lat_f,
        lng=lng_f,
        plaques=plaques,
    )


@public_bp.route("/tag/<tag_name>")
def tag_page(tag_name):
    tag_name = tag_name.strip().lower()
    page = max(1, request.args.get("page", 1, type=int))
    offset = (page - 1) * PER_PAGE
    with get_db() as db:
        tag = db.execute("SELECT * FROM tags WHERE name=?", (tag_name,)).fetchone()
        if not tag:
            abort(404)
        total = db.execute(
            "SELECT COUNT(*) FROM plaques p"
            " JOIN plaque_tags pt ON pt.plaque_id = p.id"
            " JOIN tags t ON t.id = pt.tag_id"
            " WHERE t.name=? AND p.approved=1",
            (tag_name,),
        ).fetchone()[0]
        rows = db.execute(
            "SELECT p.* FROM plaques p"
            " JOIN plaque_tags pt ON pt.plaque_id = p.id"
            " JOIN tags t ON t.id = pt.tag_id"
            " WHERE t.name=? AND p.approved=1 ORDER BY p.created_at DESC"
            " LIMIT ? OFFSET ?",
            (tag_name, PER_PAGE, offset),
        ).fetchall()
    return render_template(
        "listing.html",
        filter_type="tag",
        mode="tag",
        page_title=f"#{tag_name} — Read The Plaque",
        paginator_url=f"/tag/{tag_name}?",
        map_id="filter-map",
        list_heading="Plaques",
        name=tag_name,
        plaques=[plaque_to_dict(row) for row in rows],
        total=total,
        page=page,
        total_pages=max(1, -(-total // PER_PAGE)),
    )


@public_bp.route("/submitter/<path:submitter_name>")
def submitter_page(submitter_name):
    submitter_name = submitter_name.strip()
    page = max(1, request.args.get("page", 1, type=int))
    offset = (page - 1) * PER_PAGE
    with get_db() as db:
        total = db.execute(
            "SELECT COUNT(*) FROM plaques WHERE approved=1 AND submitted_by=?",
            (submitter_name,),
        ).fetchone()[0]
        if not total:
            abort(404)
        rows = db.execute(
            "SELECT * FROM plaques WHERE approved=1 AND submitted_by=?"
            " ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (submitter_name, PER_PAGE, offset),
        ).fetchall()
    return render_template(
        "filter.html",
        filter_type="submitter",
        mode="submitter",
        page_title=f"Submitted by {submitter_name} — Read The Plaque",
        paginator_url=f"/submitter/{quote(submitter_name, safe='')}?",
        map_id="filter-map",
        list_heading="Plaques",
        name=submitter_name,
        plaques=[plaque_to_dict(row) for row in rows],
        total=total,
        page=page,
        total_pages=max(1, -(-total // PER_PAGE)),
    )


@public_bp.route("/random")
def random_plaque():
    with get_db() as db:
        rows = db.execute("SELECT slug FROM plaques WHERE approved=1").fetchall()
    if not rows:
        abort(404)
    return redirect(url_for("public.plaque_detail", slug=random.choice(rows)["slug"]))


@public_bp.route("/about")
def about():
    return render_template("about.html")


@public_bp.route("/counts")
def counts():
    with get_db() as db:
        pending = db.execute(
            "SELECT count(*) FROM plaques WHERE approved = 0"
        ).fetchone()[0]
        approved = db.execute(
            "SELECT count(*) FROM plaques WHERE approved != 0"
        ).fetchone()[0]
    return f"Pending: {pending}; Approved: {approved}; Total: {pending + approved}"


@public_bp.route("/uploads/<path:filename>")
def uploaded_file(filename):
    if not os.path.exists(os.path.join(UPLOAD_DIR, filename)):
        return _placeholder_jpeg(filename), 200, {"Content-Type": "image/jpeg"}
    return send_from_directory(UPLOAD_DIR, filename)


@public_bp.route("/thumbs/<path:filename>")
def thumb_file(filename):
    if not os.path.exists(os.path.join(THUMB_DIR, filename)):
        return _placeholder_jpeg(filename), 200, {"Content-Type": "image/jpeg"}
    return send_from_directory(THUMB_DIR, filename)


register_submission_routes(public_bp)
