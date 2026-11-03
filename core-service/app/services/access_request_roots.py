"""The storage roots of access requests (their items), for the orchestration that may not query the database itself."""
from __future__ import annotations

from sqlalchemy import bindparam, text

from app.core.db import SessionLocal


def roots_of_requests(request_ids: list[int]) -> list[int]:
    if not request_ids:
        return []
    db = SessionLocal()
    try:
        rows = db.execute(
            text("SELECT DISTINCT target_id FROM access_request_items WHERE target_type = 'storage_root' AND access_request_id IN :ids")
            .bindparams(bindparam("ids", expanding=True)),
            {"ids": [int(x) for x in request_ids]},
        ).all()
    finally:
        db.close()
    return [int(row[0]) for row in rows]
