"""Reusable pagination helpers for list views."""

from __future__ import annotations


def clamp_page(page: int | None, minimum: int = 1) -> int:
    """Clamp page numbers to a positive integer."""
    try:
        page_int = int(page)
    except (TypeError, ValueError):
        return minimum
    return max(minimum, page_int)


def paginate(page: int | None, per_page: int) -> tuple[int, int]:
    """Return the clamped page number and SQL offset."""
    page_num = clamp_page(page)
    return page_num, (page_num - 1) * per_page


def total_pages(total: int, per_page: int) -> int:
    """Return the total number of pages for a paginated result set."""
    if total <= 0 or per_page <= 0:
        return 1
    return max(1, -(-total // per_page))
