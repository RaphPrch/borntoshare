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


def identity_source_dependency_counts_1(db: Session, params: Any, *, column_name: Any, table_name: Any) -> Any:
    """SELECT COUNT(*) FROM"""
    return db.execute(
        text(f"SELECT COUNT(*) FROM {table_name} WHERE {column_name} = :source_id"),
        params,
    )


def get_identity_source_overview_2(db: Session, params: Any, *, _LATEST_USERS: Any) -> Any:
    """SELECT COUNT(*) AS total, SUM(email IS NOT NULL AND email <> '') AS with_email FROM directory_users WHERE id I"""
    return db.execute(
        text(f"SELECT COUNT(*) AS total, SUM(email IS NOT NULL AND email <> '') AS with_email FROM directory_users WHERE id IN ({_LATEST_USERS})"),
        params,
    )


def get_identity_source_overview_3(db: Session, params: Any, *, _LATEST_GROUPS: Any) -> Any:
    """SELECT COUNT(*) FROM directory_groups WHERE id IN ("""
    return db.execute(
        text(f"SELECT COUNT(*) FROM directory_groups WHERE id IN ({_LATEST_GROUPS})"),
        params,
    )


def get_identity_source_overview_4(db: Session, params: Any, *, _GOVERNED: Any, _LATEST_GROUPS: Any) -> Any:
    """SELECT g.name, g.dn, (SELECT COUNT(*) FROM directory_group_members m WHERE m.group_id = g.id AND m.deleted_at """
    return db.execute(
        text(
                    f"""
                    SELECT g.name, g.dn,
                      (SELECT COUNT(*) FROM directory_group_members m WHERE m.group_id = g.id AND m.deleted_at IS NULL) AS members
                    FROM directory_groups g
                    WHERE g.id IN ({_LATEST_GROUPS}) AND g.name IN ({_GOVERNED})
                    ORDER BY g.name
                    """
                ),
        params,
    )


def get_identity_source_inventory_1(db: Session, params: Any, *, _GOVERNED: Any, _LATEST_GROUPS: Any) -> Any:
    """SELECT g.id, g.name, g.dn, g.description, g.external_id, (SELECT COUNT(*) FROM directory_group_members m WHERE"""
    return db.execute(
        text(
                        f"""
                        SELECT g.id, g.name, g.dn, g.description, g.external_id,
                          (SELECT COUNT(*) FROM directory_group_members m WHERE m.group_id = g.id AND m.deleted_at IS NULL) AS members,
                          g.name IN ({_GOVERNED}) AS governed
                        FROM directory_groups g
                        WHERE g.id IN ({_LATEST_GROUPS})
                          AND (:q = '%%' OR g.name LIKE :q OR g.dn LIKE :q)
                        ORDER BY governed DESC, g.name LIMIT :limit
                        """
                    ),
        params,
    )


def get_identity_source_inventory_2(db: Session, params: Any, *, _LATEST_USERS: Any) -> Any:
    """SELECT u.id, u.username, u.display_name, u.email, u.upn, u.dn, u.external_id, (SELECT COUNT(*) FROM directory_"""
    return db.execute(
        text(
                    f"""
                    SELECT u.id, u.username, u.display_name, u.email, u.upn, u.dn, u.external_id,
                      (SELECT COUNT(*) FROM directory_group_members m WHERE m.directory_user_id = u.id AND m.deleted_at IS NULL) AS groups
                    FROM directory_users u
                    WHERE u.id IN ({_LATEST_USERS})
                      AND (:q = '%%' OR u.username LIKE :q OR u.display_name LIKE :q OR u.email LIKE :q)
                    ORDER BY (u.email IS NULL OR u.email = ''), u.display_name LIMIT :limit
                    """
                ),
        params,
    )
