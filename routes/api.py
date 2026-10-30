"""JSON API routes: plaques GeoJSON, search, nearby, single plaque."""

import math

from flask import Blueprint, abort, jsonify, request

from database import get_db
from config import NEARBY_LIMIT
from models import get_tags_for_plaque, make_or_update_slug, plaque_to_dict, slugify, path_to_lat_lng_zoom

EARTH_RADIUS_KM = 6371

api_bp = Blueprint("api", __name__, url_prefix="/api")


# ── GeoJSON endpoints ──────────────────────────────────────────────────────────
@api_bp.route("/plaques/geo")
def plaques_geo():
    """Lean GeoJSON for map pins — omits image URLs to minimise payload."""
    with get_db() as db:
        rows = db.execute(
            "SELECT id, slug, title, latitude, longitude"
            " FROM plaques WHERE approved=1 ORDER BY created_at DESC"
        ).fetchall()
    features = [
        {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [r["longitude"], r["latitude"]],
            },
            "properties": {
                "id": r["id"],
                "slug": r["slug"],
                "title": r["title"],
            },
        }
        for r in rows
    ]
    return jsonify({"type": "FeatureCollection", "features": features})


@api_bp.route("/plaques")
def plaques():
    """Return all approved plaques as a GeoJSON FeatureCollection."""
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM plaques WHERE approved=1 ORDER BY created_at DESC"
        ).fetchall()
    features = []
    for r in rows:
        d = plaque_to_dict(r)
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [d["longitude"], d["latitude"]],
                },
                "properties": d,
            }
        )
    return jsonify({"type": "FeatureCollection", "features": features})


# ── Search ─────────────────────────────────────────────────────────────────────
@api_bp.route("/search")
def search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])
    like = f"%{q}%"
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM plaques WHERE approved=1"
            " AND (title LIKE ? OR description LIKE ?)"
            " ORDER BY created_at DESC LIMIT 30",
            (like, like),
        ).fetchall()
    return jsonify([plaque_to_dict(r) for r in rows])


# ── Nearby ─────────────────────────────────────────────────────────────────────
def _get_closest_plaques(lat: float, lng: float, limit: int = NEARBY_LIMIT, search_width_deg: float = 0.018, exclude_id: int = -1):
    # Pre-calculate target constants
    lat_rad = math.radians(lat)
    lng_rad = math.radians(lng)

    closest_plaques = []

    # Start with a small search window and expand if expand if not enough found
    with get_db() as db:
        while len(closest_plaques) < limit:
            lat_min = max(lat - search_width_deg, -90.0)
            lat_max = min(lat + search_width_deg, 90.0)
            lng_min = max(lng - search_width_deg, -180.0)
            lng_max = min(lng + search_width_deg, 180.0)

            # Law of Cosines sort inside the indexed bounding box
            query = f"""
                SELECT *,
                       ({EARTH_RADIUS_KM} * acos(
                           sin(?) * sin(radians(latitude)) +
                           cos(?) * cos(radians(latitude)) * cos(radians(longitude) - ?)
                       )) AS distance_km
                FROM plaques
                WHERE approved = 1
                  AND latitude BETWEEN ? AND ?
                  AND longitude BETWEEN ? AND ?
                  AND id != ?
                ORDER BY distance_km ASC
                LIMIT ?;
            """

            closest_plaques = db.execute(query, (
                lat_rad, lat_rad, lng_rad,
                lat_min, lat_max,
                lng_min, lng_max,
                exclude_id,
                limit
            )).fetchall()

            # If not enough plaques were found, 10x the search area (~3.2x width).
            # The last pass is capped at 360° so it covers the whole globe from any
            # starting longitude; if even that finds fewer than `limit`, stop.
            if len(closest_plaques) < limit:
                if search_width_deg >= 360:
                    break
                search_width_deg = min(search_width_deg * 3.2, 360.0)

    results = []
    for r in closest_plaques:
        d = plaque_to_dict(r)
        d["distance_km"] = r["distance_km"]
        results.append(d)

    return results


@api_bp.route("/nearby/<path:coords>")
def nearby_location(coords):
    """Return the NEARBY_LIMIT nearest approved plaques, sorted by distance."""
    lat, lng, _ = path_to_lat_lng_zoom(coords)
    closest_plaques = _get_closest_plaques(lat, lng)
    return jsonify(closest_plaques[:NEARBY_LIMIT])


@api_bp.route("/nearby/<int:plaque_id>")
def nearby(plaque_id):
    """Return the NEARBY_LIMIT nearest approved plaques, sorted by distance."""

    with get_db() as db:
        plaque = db.execute(
            "SELECT latitude, longitude FROM plaques WHERE id=? AND approved=1",
            (plaque_id,),
        ).fetchone()
        if not plaque:
            abort(404)
        lat, lng = plaque["latitude"], plaque["longitude"]
        closest_plaques = _get_closest_plaques(lat, lng, exclude_id=plaque_id)

    return jsonify(closest_plaques[:NEARBY_LIMIT])


# ── Slug check ───────────────────────────────────────────────────────────────────
@api_bp.route("/slug")
def slug_check():
    """Convert a title to a slug and report whether it is already taken.

    Uses the same slugify() / make_or_update_slug() as /submit and
    /admin/edit, so the answer always matches what would actually be saved.
    """
    title = request.args.get("title", "").strip()
    if not title:
        return jsonify({"error": "title required"}), 400
    base = slugify(title)
    with get_db() as db:
        slug = make_or_update_slug(db, title)
        taken = slug != base  # the unique slug only differs if base is in use
        existing = None
        if taken:
            existing = db.execute(
                "SELECT title, slug, approved FROM plaques WHERE slug=?", (base,)
            ).fetchone()
    return jsonify(
        {
            "slug": slug,
            "base_slug": base,
            "exists": taken,
            "existing_title": existing["title"] if existing else None,
            # Only link to the page if it is public (unapproved pages 404)
            "existing_url": (
                f"/plaque/{existing['slug']}" if existing and existing["approved"] else None
            ),
        }
    )


# ── Single plaque ──────────────────────────────────────────────────────────────
@api_bp.route("/plaques/<int:plaque_id>")
def plaque(plaque_id):
    """Return one approved plaque by ID, with tags."""
    with get_db() as db:
        row = db.execute(
            "SELECT * FROM plaques WHERE id=? AND approved=1", (plaque_id,)
        ).fetchone()
        if not row:
            abort(404)
        tags = get_tags_for_plaque(db, plaque_id)
    d = plaque_to_dict(row)
    d["tags"] = tags
    return jsonify(d)
