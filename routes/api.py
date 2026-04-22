"""JSON API routes: plaques GeoJSON, search, nearby, single plaque."""

import math

from flask import Blueprint, abort, jsonify, request

from database import get_db
from config import NEARBY_LIMIT
from models import get_tags_for_plaque, plaque_to_dict

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
        dlat = 1.8
        dlng = dlat / max(math.cos(math.radians(lat)), 0.01)

        candidates = db.execute(
            "SELECT * FROM plaques WHERE approved=1 AND id != ?"
            " AND latitude  BETWEEN ? AND ?"
            " AND longitude BETWEEN ? AND ?"
            f" LIMIT {NEARBY_LIMIT}",
            (plaque_id, lat - dlat, lat + dlat, lng - dlng, lng + dlng),
        ).fetchall()

    def haversine(lat1, lng1, lat2, lng2):
        R = 6371
        dlat = math.radians(lat2 - lat1)
        dlng = math.radians(lng2 - lng1)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(lat1))
            * math.cos(math.radians(lat2))
            * math.sin(dlng / 2) ** 2
        )
        return R * 2 * math.asin(math.sqrt(a))

    ranked = sorted(
        candidates,
        key=lambda r: haversine(lat, lng, r["latitude"], r["longitude"]),
    )

    results = []
    for r in ranked:
        d = plaque_to_dict(r)
        d["distance_km"] = round(haversine(lat, lng, r["latitude"], r["longitude"]), 2)
        results.append(d)

    return jsonify(results)


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
