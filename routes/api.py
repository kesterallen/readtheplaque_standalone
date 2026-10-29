"""JSON API routes: plaques GeoJSON, search, nearby, single plaque."""

import math

from flask import Blueprint, abort, jsonify, request

from database import get_db
from config import NEARBY_LIMIT
from models import get_tags_for_plaque, plaque_to_dict

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
# TODO

def _get_closest_plaques(target_lat: float, target_lng: float, limit: int = 10, search_degree_radius: float = 0.018, exclude_id: int = -1):
    # Pre-calculate target constants
    target_lat_rad = math.radians(target_lat)
    target_lng_rad = math.radians(target_lng)

    closest_plaques = []

    # Start with a small search window and expand if expand if not enough found
    with get_db() as db:
        while len(closest_plaques) < limit and search_degree_radius < 180:
            lat_min = target_lat - search_degree_radius
            lat_max = target_lat + search_degree_radius
            lng_min = target_lng - search_degree_radius
            lng_max = target_lng + search_degree_radius

            # Law of Cosines sort inside the indexed bounding box
            query = f"""
                SELECT *,
                       ({EARTH_RADIUS_KM} * acos(
                           sin(?) * sin(radians(latitude)) +
                           cos(?) * cos(radians(latitude)) * cos(radians(longitude) - ?)
                       )) AS distance_km
                FROM plaques
                WHERE latitude BETWEEN ? AND ?
                  AND longitude BETWEEN ? AND ?
                  AND id != ?
                ORDER BY distance_km ASC
                LIMIT ?;
            """

            closest_plaques = db.execute(query, (
                target_lat_rad, target_lat_rad, target_lng_rad,
                lat_min, lat_max,
                lng_min, lng_max,
                exclude_id,
                limit
            )).fetchall()

            # If not enough plaques were found, enlarge the search radius and try again
            if len(closest_plaques) < limit:
                search_degree_radius *= 3

    return closest_plaques


@api_bp.route("/nearby/<int:plaque_id>")
def nearby(plaque_id):
    """Return the NEARBY_LIMIT nearest approved plaques, sorted by distance."""

    with get_db() as db:
        origin = db.execute(
            "SELECT latitude, longitude FROM plaques WHERE id=? AND approved=1",
            (plaque_id,),
        ).fetchone()
        if not origin:
            abort(404)
        lat, lng = origin["latitude"], origin["longitude"]
        sorted_candidates = _get_closest_plaques(lat, lng, NEARBY_LIMIT, exclude_id=plaque_id)

    results = []
    for r in sorted_candidates:
        d = plaque_to_dict(r)
        d["distance_km"] = r["distance_km"]
        results.append(d)

    return jsonify(results[:NEARBY_LIMIT])


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
