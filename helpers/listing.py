"""Shared rendering helpers for paginated list views."""

from __future__ import annotations

from helpers.pagination import total_pages
from models import plaque_to_dict


def paginated_rows_context(
    rows,
    total: int,
    page: int,
    per_page: int,
    *,
    rows_key: str = "plaques",
) -> dict[str, object]:
    """Return the common template context for paginated plaque lists."""
    return {
        rows_key: [plaque_to_dict(row) for row in rows],
        "total": total,
        "page": page,
        "total_pages": total_pages(total, per_page),
    }
