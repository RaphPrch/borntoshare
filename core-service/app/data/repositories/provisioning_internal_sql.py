"""SQL of the routes of api/provisioning_internal.py, moved out of them unchanged: each function runs the statement the route
ran and returns the same result (the routes hold no SQL)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def persist_identity_source_probe_result_1(db: Session, params: Any) -> Any:
    """UPDATE identity_sources SET last_probe_at = :last_probe_at, last_probe_message = :last_probe_message, status ="""
    return db.execute(
        text(
                    """
                    UPDATE identity_sources
                    SET last_probe_at = :last_probe_at,
                        last_probe_message = :last_probe_message,
                        status = COALESCE(:status, status),
                        updated_at = :updated_at
                    WHERE id = :identity_source_id
                    """
                ),
        params,
    )
