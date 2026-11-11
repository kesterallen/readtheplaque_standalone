"""Public-facing routes: homepage, plaque detail, map, submit, tag, random, about."""

import random
import re
from urllib.parse import quote

from markupsafe import Markup
from flask import (
    Blueprint,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)

from config import (
    HCAPTCHA_SITEKEY,
    MAX_FILE_MB,
    MAX_UPLOAD_MB,
    PER_PAGE,
    SHARE_IMAGE_MAX_MB,
    SITE_URL,
    THUMB_DIR,
    UPLOAD_DIR,
)
from routes.api import _get_closest_plaques
from services.images import cleanup_saved_images, save_images
from services.submissions import create_submission
from spam import (
    check_content,
    check_honeypot,
    check_rate_limit,
    HONEYPOT_FIELD,
    verify_captcha,
)
from database import get_db
from models import (
    _placeholder_jpeg,
    get_images_for_plaque,
    get_tags_for_plaque,
    image_url,
    parse_tags,
    plaque_to_dict,
    sanitise_description,
    path_to_lat_lng_zoom,
    subdir_path,
    thumb_url,
)

import os

public_bp = Blueprint("public", __name__)


# ── Homepage ───────────────────────────────────────────────────────────────────
@public_bp.route("/")
@public_bp.route("/page/<int:page>")
def index(page=1):
    # A page in the URL path (/page/2) takes precedence over a query parameter.
    route_page = (request.view_args or {}).get("page")
    page = max(1, route_page if route_page is not None else request.args.get("page", 1, type=int))
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
            " ORDER BY created_at DESC"
            " LIMIT ? OFFSET ?",
            (featured_id or -1, PER_PAGE, offset),
        ).fetchall()

    featured = plaque_to_dict(featured_row) if featured_row else None
    recent = [plaque_to_dict(r) for r in rows]
    # The featured plaque is shown separately on every page, not in the
    # paginated recent list. Exclude it when calculating recent-list pages.
    recent_total = max(0, total - (1 if featured_row else 0))
    total_pages = max(1, -(-recent_total // PER_PAGE))

    return render_template(
        "index.html",
        featured=featured,
        recent=recent,
        total=total,
        page=page,
        total_pages=total_pages,
    )


# ── RSS Feed ──────────────────────────────────────────────────────────────────
@public_bp.route("/rss")
@public_bp.route("/feed")
def feed():
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM plaques WHERE approved=1 ORDER BY created_at DESC LIMIT ?",
            (PER_PAGE,),
        ).fetchall()
    recent = [plaque_to_dict(r) for r in rows]
    return render_template(
        "feed.xml",
        recent=recent,
    )


# ── Map ───────────────────────────────────────────────────────────────────────
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


# ── Submit ────────────────────────────────────────────────────────────────────
@public_bp.route("/submit", methods=["GET", "POST"])
def submit():
    if request.method == "GET":
        return render_template(
            "submit.html",
            #hcaptcha_sitekey=HCAPTCHA_SITEKEY, # TODO: turn this on for hcaptcha
            honeypot_field=HONEYPOT_FIELD,
            max_file_mb=MAX_FILE_MB,
            max_upload_mb=MAX_UPLOAD_MB,
        )

    # ── Spam checks ────────────────────────────────────────────────────────────
    # Honeypot — bots fill this hidden field, humans never see it
    if check_honeypot(request.form):
        return jsonify(
            {"ok": True, "slug": "pending", "pending": True}
        )  # silent discard

    # Rate limit
    ip = (
        request.headers.get("X-Forwarded-For", request.remote_addr or "")
        .split(",")[0]
        .strip()
    )
    rate_ok, rate_err = check_rate_limit(ip)
    if not rate_ok:
        return jsonify({"ok": False, "errors": [rate_err]}), 429

    # TODO: turn this on for hcaptcha
    ## hCaptcha
    #captcha_token = request.form.get("h-captcha-response", "")
    #captcha_ok, captcha_err = verify_captcha(captcha_token)
    #if not captcha_ok:
    #    return jsonify({"ok": False, "errors": [captcha_err]}), 400

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

    # Content spam check
    content_ok, content_err = check_content(title, description)
    if not content_ok:
        errors.append(content_err)

    image_files = request.files.getlist("images")
    saved_images, img_errors = save_images(image_files)
    errors.extend(img_errors)

    if not saved_images or errors:
        cleanup_saved_images(saved_images)
        return jsonify(
            {"ok": False, "errors": errors or ["No images could be saved."]}
        ), 400

    # created_at / updated_at let the admin-run importer keep a plaque's original
    # dates. Anonymous visitors must not set them: a future date would pin their
    # plaque to the top of "most recent" forever, and a past one would hide it.
    if session.get("admin") is True:
        created_at = request.form.get("created_at", None)
        updated_at = request.form.get("updated_at", None)
    else:
        created_at = updated_at = None

    try:
        plaque_id, slug = create_submission(
            title=title,
            description=description,
            latitude=lat,
            longitude=lng,
            submitted_by=submitted_by,
            created_at=created_at,
            updated_at=updated_at,
            saved_images=saved_images,
            tag_names=tag_names,
        )
    except Exception:
        cleanup_saved_images(saved_images)
        raise

    resp = {"ok": True, "slug": slug, "pending": True, "lat": lat, "lng": lng}
    return jsonify(resp)


# ── Plaque detail ─────────────────────────────────────────────────────────────
# ── Link previews ─────────────────────────────────────────────────────────────
def _site_root() -> str:
    """Absolute address of this site; share tags need full URLs, not paths.

    $SITE_URL if set, else the address this request came in on, using https when
    Fly's proxy reports the visitor did (Flask itself only ever sees plain http).
    """
    if SITE_URL:
        return SITE_URL
    scheme = request.headers.get("X-Forwarded-Proto", request.scheme).split(",")[0].strip()
    if scheme not in ("http", "https"):
        scheme = request.scheme
    return f"{scheme}://{request.host}"


def _share_description(raw: str | None, limit: int = 200) -> str:
    """Plain-text summary of a plaque's text for a preview card."""
    text = Markup(raw or "").striptags()  # drops tags, decodes &amp; etc.
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0].rstrip(" ,.;:-–—") + "…"
    return text or "A plaque on Read The Plaque, a map of the world's historical plaques."


def _share_image(plaque: dict) -> tuple[str, str]:
    """Pick the preview image. Returns (absolute URL, X card type).

    The full photo gives a big preview card, but only if Facebook and X will
    fetch it (see SHARE_IMAGE_MAX_MB); otherwise use the thumbnail.
    """
    try:
        size = os.path.getsize(subdir_path(UPLOAD_DIR, plaque["image_file"]))
    except OSError:
        size = None
    if size is not None and size <= SHARE_IMAGE_MAX_MB * 1024 * 1024:
        return _site_root() + plaque["image_url"], "summary_large_image"
    return _site_root() + plaque["thumb_url"], "summary"


@public_bp.route("/plaque/<slug>/propose-fix", methods=["POST"])
def propose_plaque_fix(slug):
    """Let visitors flag an error on an approved plaque and explain the issue."""
    with get_db() as db:
        plaque = db.execute(
            "SELECT id FROM plaques WHERE slug=? AND approved=1", (slug,)
        ).fetchone()
        if not plaque:
            abort(404)

        comment = request.form.get("comment", "").strip()
        if not comment:
            flash("Please add a comment explaining the proposed fix.", "error")
        elif len(comment) > 2000:
            flash("Please keep the comment to 2,000 characters or fewer.", "error")
        else:
            db.execute(
                "INSERT INTO proposed_plaque_fixes (plaque_id, comment) VALUES (?, ?)",
                (plaque["id"], comment),
            )
            flash(
                "Thank you. Your proposed fix has been sent to the site administrators.",
                "success",
            )

    return redirect(url_for("public.plaque_detail", slug=slug) + "#propose-fix")


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


# ── Search results page ───────────────────────────────────────────────────────
@public_bp.route("/search")
@public_bp.route("/search/<int:page>") # TODO: make this route work
def search_page(page=1):
    # A page in the URL path (/search/2) takes precedence over a query parameter.
    route_page = (request.view_args or {}).get("page")
    page = max(1, route_page if route_page is not None else request.args.get("page", 1, type=int))
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

        # TODO: note this seaches title AND description, might want to be able to limit to title-only
        rows = db.execute(
            "SELECT * FROM plaques WHERE approved=1"
            " AND (title LIKE ? OR description LIKE ?)"
            " ORDER BY created_at DESC"
            " LIMIT ? OFFSET ?",
            (like, like, PER_PAGE, offset),
        ).fetchall()
    plaques = [plaque_to_dict(r) for r in rows]
    total_pages = max(1, -(-total // PER_PAGE))
    return render_template(
        "listing.html",
        mode="search",
        page_title=f"Search: {q} — Read The Plaque",
        paginator_url=url_for("public.search_page", q=q),
        map_id="search-map",
        list_heading="Results",
        q=q,
        plaques=plaques,
        total=total,
        page=page,
        total_pages=total_pages,
    )

# ── Random plaques gallery ────────────────────────────────────────────────────
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


# ── Nearby-me gallery ─────────────────────────────────────────────────────────
@public_bp.route("/nearby/<lat>/<lng>")
def nearby_gallery(lat, lng):
    """The PER_PAGE approved plaques nearest to (lat, lng), closest first."""
    # Validated strictly (404, not clamped) because every lat/lng pair is a URL.
    # Not <float:...>, which rejects negatives and whole numbers.
    try:
        lat_f, lng_f = float(lat), float(lng)
    except ValueError:
        abort(404)
    # Written as `not (in range)` so NaN, which compares False, is rejected too.
    if not (-90 <= lat_f <= 90 and -180 <= lng_f <= 180):
        abort(404)

    plaques = _get_closest_plaques(lat_f, lng_f, limit=PER_PAGE)
    for p in plaques:
        km = p.get("distance_km") or 0.0  # SQLite acos() is NULL on an exact match
        p["distance_km"] = round(km, 1)
        p["distance_mi"] = round(km / 1.609344, 1)
    return render_template(
        "listing.html",
        mode="nearby",
        page_title= "Plaques near you — Read The Plaque",
        paginator_url = None,
        map_id="nearby-map",
        list_heading="Nearest first",
        lat=lat_f,
        lng=lng_f,
        plaques=plaques,
    )


# ── Tag page ──────────────────────────────────────────────────────────────────
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
    plaques = [plaque_to_dict(r) for r in rows]
    total_pages = max(1, -(-total // PER_PAGE))
    return render_template(
        "listing.html",
        filter_type="tag",
        mode="tag",
        page_title=f"#{tag_name} — Read The Plaque",
        paginator_url=url_for("public.tag_page", tag_name=tag_name),
        map_id="filter-map",
        list_heading="Plaques",
        name=tag_name,
        plaques=plaques,
        total=total,
        page=page,
        total_pages=total_pages,
    )


# ── Submitter page ────────────────────────────────────────────────────────────
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
    plaques = [plaque_to_dict(r) for r in rows]
    total_pages = max(1, -(-total // PER_PAGE))
    return render_template(
        "listing.html",
        filter_type="submitter",
        mode="submitter",
        page_title=f"Submitted by {submitter_name} — Read The Plaque",
        paginator_url=url_for("public.submitter_page", submitter_name=submitter_name),
        map_id="filter-map",
        list_heading="Plaques",
        name=submitter_name,
        plaques=plaques,
        total=total,
        page=page,
        total_pages=total_pages,
    )


# ── Random, About, Counts ────────────────────────────────────────────────────────────
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


@public_bp.route("/counts")
def counts():
    with get_db() as db:
        pending = db.execute("SELECT count(*) FROM plaques WHERE approved = 0").fetchone()[0]
        approved = db.execute("SELECT count(*) FROM plaques WHERE approved != 0").fetchone()[0]
    return f"Pending: {pending}; Approved: {approved}; Total: {pending + approved}"


# ── File serving ──────────────────────────────────────────────────────────────
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
