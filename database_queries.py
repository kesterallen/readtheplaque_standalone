"""Focused SQLite query helpers shared by route modules.

These functions accept an open database connection and return rows/counts; they
leave transaction and connection lifetime management to callers.
"""

from __future__ import annotations

import sqlite3

ADMIN_SORT_COLUMNS = {
    "title": "title",
    "created_at": "created_at",
    "updated_at": "updated_at",
    "submitted_by": "submitted_by",
    "approved": "approved",
}


def count_plaques(db: sqlite3.Connection, *, approved: bool | None = None) -> int:
    """Count plaques, optionally restricted to approved or pending records."""
    if approved is None:
        row = db.execute("SELECT COUNT(*) FROM plaques").fetchone()
    else:
        row = db.execute(
            "SELECT COUNT(*) FROM plaques WHERE approved=?", (int(approved),)
        ).fetchone()
    return row[0]


def get_featured_plaque(db: sqlite3.Connection):
    """Get the featured approved plaque, falling back to the newest approved one."""
    row = db.execute(
        "SELECT * FROM plaques WHERE approved=1 AND is_featured=1 LIMIT 1"
    ).fetchone()
    if row is None:
        row = db.execute(
            "SELECT * FROM plaques WHERE approved=1 ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    return row


def list_approved_plaque_page(
    db: sqlite3.Connection,
    *,
    limit: int,
    offset: int,
    exclude_id: int | None = None,
):
    """List approved plaques newest-first, optionally excluding one plaque."""
    if exclude_id is None:
        return db.execute(
            "SELECT * FROM plaques WHERE approved=1 ORDER BY created_at DESC"
            " LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    return db.execute(
        "SELECT * FROM plaques WHERE approved=1 AND id != ?"
        " ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (exclude_id, limit, offset),
    ).fetchall()


def search_approved_plaques(
    db: sqlite3.Connection, query: str, *, limit: int, offset: int
) -> tuple[int, list[sqlite3.Row]]:
    """Search approved plaque titles/descriptions and return count plus page."""
    pattern = f"%{query}%"
    where = "approved=1 AND (title LIKE ? OR description LIKE ?)"
    params = (pattern, pattern)
    total = db.execute(
        f"SELECT COUNT(*) FROM plaques WHERE {where}", params
    ).fetchone()[0]
    rows = db.execute(
        f"SELECT * FROM plaques WHERE {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (*params, limit, offset),
    ).fetchall()
    return total, rows


def list_tag_page(
    db: sqlite3.Connection, tag_name: str, *, limit: int, offset: int
) -> tuple[bool, int, list[sqlite3.Row]]:
    """Return whether the tag exists, its approved plaque count, and a page."""
    tag = db.execute("SELECT 1 FROM tags WHERE name=?", (tag_name,)).fetchone()
    if tag is None:
        return False, 0, []

    joins = (
        " FROM plaques p"
        " JOIN plaque_tags pt ON pt.plaque_id=p.id"
        " JOIN tags t ON t.id=pt.tag_id"
        " WHERE t.name=? AND p.approved=1"
    )
    total = db.execute("SELECT COUNT(*)" + joins, (tag_name,)).fetchone()[0]
    rows = db.execute(
        "SELECT p.*" + joins + " ORDER BY p.created_at DESC LIMIT ? OFFSET ?",
        (tag_name, limit, offset),
    ).fetchall()
    return True, total, rows


def list_submitter_page(
    db: sqlite3.Connection, submitter: str, *, limit: int, offset: int
) -> tuple[int, list[sqlite3.Row]]:
    """Return an approved submitter's plaque count and newest-first page."""
    params = (submitter,)
    total = db.execute(
        "SELECT COUNT(*) FROM plaques WHERE approved=1 AND submitted_by=?", params
    ).fetchone()[0]
    rows = db.execute(
        "SELECT * FROM plaques WHERE approved=1 AND submitted_by=?"
        " ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (*params, limit, offset),
    ).fetchall()
    return total, rows


def list_pending_page(db: sqlite3.Connection, *, limit: int, offset: int):
    """Return pending plaque count and oldest-first page."""
    total = count_plaques(db, approved=False)
    rows = db.execute(
        "SELECT * FROM plaques WHERE approved=0 ORDER BY created_at ASC"
        " LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    return total, rows


def list_admin_plaque_page(
    db: sqlite3.Connection,
    *,
    status: str,
    query: str,
    sort: str,
    direction: str,
    limit: int,
    offset: int,
) -> tuple[int, list[sqlite3.Row], str, str]:
    """Return an admin plaque count/page using only whitelisted SQL fragments."""
    sort = sort if sort in ADMIN_SORT_COLUMNS else "created_at"
    direction = direction.lower()
    if direction not in {"asc", "desc"}:
        direction = "desc"

    clauses: list[str] = []
    params: list[object] = []
    if status == "approved":
        clauses.append("approved=1")
    elif status == "pending":
        clauses.append("approved=0")
    if query:
        clauses.append("title LIKE ?")
        params.append(f"%{query}%")

    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    total = db.execute(f"SELECT COUNT(*) FROM plaques{where}", params).fetchone()[0]
    rows = db.execute(
        f"SELECT * FROM plaques{where} ORDER BY {ADMIN_SORT_COLUMNS[sort]} {direction.upper()}"
        " LIMIT ? OFFSET ?",
        (*params, limit, offset),
    ).fetchall()
    return total, rows, sort, direction
