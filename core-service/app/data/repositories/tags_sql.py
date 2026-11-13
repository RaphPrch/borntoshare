"""SQL of the routes of api/tags.py, moved out of them unchanged: each function runs the statement the route
ran and returns the same result (the routes hold no SQL)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def tags_overview_1(db: Session) -> Any:
    """SELECT srt.tag_id, sr.id, sr.name, sr.root_path, se.name AS server FROM storage_root_tags srt JOIN storage_roo"""
    return db.execute(
        text(
                    """
                    SELECT srt.tag_id, sr.id, sr.name, sr.root_path, se.name AS server
                    FROM storage_root_tags srt
                    JOIN storage_roots sr ON sr.id = srt.storage_root_id AND sr.deleted_at IS NULL
                    JOIN storage_endpoints se ON se.id = sr.storage_endpoint_id
                    ORDER BY sr.name
                    """
                ),
    )


def merge_tag_1(db: Session, params: Any) -> Any:
    """INSERT IGNORE INTO storage_root_tags (storage_root_id, tag_id) SELECT storage_root_id, :target FROM storage_ro"""
    return db.execute(
        text(
                    """
                    INSERT IGNORE INTO storage_root_tags (storage_root_id, tag_id)
                    SELECT storage_root_id, :target FROM storage_root_tags WHERE tag_id = :source
                    """
                ),
        params,
    )


def attachment_names_1(db: Session, params: Any) -> Any:
    """SELECT name, root_path FROM storage_roots WHERE id = :id"""
    return db.execute(
        text("SELECT name, root_path FROM storage_roots WHERE id = :id"),
        params,
    )


# ---- tag links of folders (SQLAlchemy Core statements of the routes) ----
def tag_has_links(db: Session, tag_id: int) -> bool:
    from sqlalchemy import select

    from app.data.models.storage_root_tag import storage_root_tag

    return db.execute(select(storage_root_tag.c.tag_id).where(storage_root_tag.c.tag_id == tag_id).limit(1)).first() is not None


def drop_tag_links(db: Session, tag_id: int) -> None:
    from app.data.models.storage_root_tag import storage_root_tag

    db.execute(storage_root_tag.delete().where(storage_root_tag.c.tag_id == int(tag_id)))


def link(db: Session, table: Any, resource_col: str, resource_id: int, tag_id: int) -> None:
    """Adds the link (raises IntegrityError when it exists: the route treats it as already attached)."""
    db.execute(table.insert().values({resource_col: int(resource_id), "tag_id": int(tag_id)}))


def unlink(db: Session, table: Any, resource_col: str, resource_id: int, tag_id: int) -> None:
    db.execute(table.delete().where((table.c[resource_col] == int(resource_id)) & (table.c.tag_id == int(tag_id))))
