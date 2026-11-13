"""SQL of the routes of api/identity_sources.py, moved out of them unchanged: each function runs the statement the route
ran and returns the same result (the routes hold no SQL)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def ensure_unique_source_1(db: Session, params: Any) -> Any:
    """SELECT id FROM identity_sources WHERE LOWER(TRIM(name)) = LOWER(TRIM(:name)) AND id <> :exclude_id LIMIT 1"""
    return db.execute(
        text(
                        "SELECT id FROM identity_sources WHERE LOWER(TRIM(name)) = LOWER(TRIM(:name)) AND id <> :exclude_id LIMIT 1"
                    ),
        params,
    )


def ensure_unique_source_2(db: Session, params: Any) -> Any:
    """SELECT name FROM identity_sources WHERE LOWER(TRIM(domain_name)) = LOWER(TRIM(:domain_name)) AND LOWER(type) ="""
    return db.execute(
        text(
                        """
                        SELECT name FROM identity_sources
                        WHERE LOWER(TRIM(domain_name)) = LOWER(TRIM(:domain_name))
                          AND LOWER(type) = 'ad' AND auth_enabled = 1 AND is_active = 1 AND id <> :exclude_id
                        LIMIT 1
                        """
                    ),
        params,
    )


def delete_identity_source_1(db: Session, params: Any) -> Any:
    """DELETE FROM infra_component_status WHERE component = :c"""
    return db.execute(
        text("DELETE FROM infra_component_status WHERE component = :c"),
        params,
    )


def get_identity_source_overview_1(db: Session, params: Any) -> Any:
    """SELECT id, name, endpoint_type, host, (SELECT COUNT(*) FROM storage_roots r WHERE r.storage_endpoint_id = e.id"""
    return db.execute(
        text(
                    """
                    SELECT id, name, endpoint_type, host,
                      (SELECT COUNT(*) FROM storage_roots r WHERE r.storage_endpoint_id = e.id) AS roots
                    FROM storage_endpoints e WHERE identity_source_id = :id ORDER BY endpoint_type <> 'smb', name
                    """
                ),
        params,
    )
