"""Database operations for creating a submitted plaque."""

from database import get_db
from models import make_or_update_slug, set_tags_for_plaque


def create_submission(
    *,
    title: str,
    description: str,
    latitude: float,
    longitude: float,
    submitted_by: str,
    created_at: str | None,
    updated_at: str | None,
    saved_images: list[dict],
    tag_names: list[str],
) -> tuple[int, str]:
    """Insert a pending plaque, its images, and tags in one DB transaction."""
    if not saved_images:
        raise ValueError("A submission must contain at least one saved image.")

    with get_db() as db:
        primary = saved_images[0]
        slug = make_or_update_slug(db, title)

        columns = [
            "slug", "title", "description", "latitude", "longitude",
            "image_file", "thumb_file", "submitted_by", "approved",
        ]
        values = [
            slug, title, description, latitude, longitude,
            primary["filename"], primary["thumb"], submitted_by, 0,
        ]
        if created_at is not None:
            columns.append("created_at")
            values.append(created_at)
        if updated_at is not None:
            columns.append("updated_at")
            values.append(updated_at)

        placeholders = ", ".join("?" for _ in columns)
        cursor = db.execute(
            f"INSERT INTO plaques ({', '.join(columns)}) VALUES ({placeholders})",
            values,
        )
        plaque_id = cursor.lastrowid

        for index, image in enumerate(saved_images):
            db.execute(
                "INSERT INTO plaque_images "
                "(plaque_id, image_file, thumb_file, image_hash, is_primary, sort_order) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    plaque_id, image["filename"], image["thumb"], image["hash"],
                    1 if index == 0 else 0, index,
                ),
            )

        set_tags_for_plaque(db, plaque_id, tag_names)

    return plaque_id, slug
