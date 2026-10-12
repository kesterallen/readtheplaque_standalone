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

    def _equirectangular_distance_proxy(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """
        Fast version of equirectangular distance for sorting -- ignore
        earth radius and skip the square root for computational spped
        """

        # Equirectangular approximation formula
        dx = math.radians(lng2 - lng1) * math.cos(math.radians(lat1 + lat2) / 2.0)
        dy = math.radians(lat2 - lat1)

        distance_dividedbyR_squared  = dx**2 + dy**2
        return distance_dividedbyR_squared

    def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """ Distance in km between (lat1, lng1) and (lat2, lng2)"""
        earth_radius_km = 6371
        dlat = math.radians(lat2 - lat1)
        dlng = math.radians(lng2 - lng1)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(lat1))
            * math.cos(math.radians(lat2))
            * math.sin(dlng / 2) ** 2
        )
        return earth_radius_km * 2 * math.asin(math.sqrt(a))

    # TODO: start with a smaller NEARBY_LIMIT, and expand if there aren't enough plaques?
    # ?
    # dlat = 0.018 -> 0.018 degrees of latitude ~ 2 km
    # dlat = 1.8 -> 1.8 degrees of latitude ~ 200 km
    dlats = [0.018, 1.8]
    for dlat in dlats:
        with get_db() as db:
            origin = db.execute(
                "SELECT latitude, longitude FROM plaques WHERE id=? AND approved=1",
                (plaque_id,),
            ).fetchone()
            if not origin:
                abort(404)

            lat, lng = origin["latitude"], origin["longitude"]
            dlng = dlat / max(math.cos(math.radians(lat)), 0.01)

            candidates = db.execute(
                "SELECT * FROM plaques WHERE approved=1 AND id != ?"
                " AND latitude  BETWEEN ? AND ?"
                " AND longitude BETWEEN ? AND ?"
                f" LIMIT {NEARBY_LIMIT}",
                (plaque_id, lat - dlat, lat + dlat, lng - dlng, lng + dlng),
            ).fetchall()
        if len(candidates) >= NEARBY_LIMIT:
            break

    ranked = sorted(
        candidates,
        key=lambda r: _equirectangular_distance_proxy(lat, lng, r["latitude"], r["longitude"]),
        # TODO: previously used this _haversine call, but the _equirectangular_distance_proxy is faster:
        #key=lambda r: _haversine(lat, lng, r["latitude"], r["longitude"]),
    )

    results = []
    for r in ranked:
        d = plaque_to_dict(r)
        d["distance_km"] = round(_haversine(lat, lng, r["latitude"], r["longitude"]), 2)
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
