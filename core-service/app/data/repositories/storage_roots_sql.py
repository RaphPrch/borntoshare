"""SQL of the routes of api/storage_roots.py, moved out of them unchanged: each function runs the statement the route
ran and returns the same result (the routes hold no SQL)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def load_active_enabled_snapshot_users_1(db: Session, params: Any) -> Any:
    """SELECT DISTINCT ib.identity_id FROM directory_snapshots ds JOIN directory_snapshot_users dsu ON dsu.snapshot_i"""
    return db.execute(
        text(
                    """
                    SELECT DISTINCT ib.identity_id
                    FROM directory_snapshots ds
                    JOIN directory_snapshot_users dsu
                      ON dsu.snapshot_id = ds.id
                    JOIN directory_users du
                      ON du.identity_source_id = dsu.identity_source_id
                     AND (
                          LOWER(TRIM(COALESCE(du.external_id, ''))) = LOWER(TRIM(COALESCE(dsu.external_id, '')))
                       OR LOWER(TRIM(COALESCE(du.dn, ''))) = LOWER(TRIM(COALESCE(dsu.dn, '')))
                     )
                    JOIN identity_bindings ib
                      ON ib.directory_user_id = du.id
                    WHERE ds.identity_source_id = :identity_source_id
                      AND UPPER(COALESCE(ds.status, '')) IN ('ACTIVE', 'SUCCEEDED')
                      AND COALESCE(dsu.is_active, 0) = 1
                      AND COALESCE(ib.identity_id, 0) > 0
                    """
                ),
        params,
    )


def guardians_in_active_snapshot_enabled_1(db: Session, params: Any) -> Any:
    """SELECT se.identity_source_id FROM storage_roots sr JOIN storage_endpoints se ON se.id = sr.storage_endpoint_id"""
    return db.execute(
        text(
                    """
                    SELECT se.identity_source_id
                    FROM storage_roots sr
                    JOIN storage_endpoints se ON se.id = sr.storage_endpoint_id
                    WHERE sr.id = :storage_root_id
                    LIMIT 1
                    """
                ),
        params,
    )


def load_existing_guardian_ids_1(db: Session, params: Any) -> Any:
    """SELECT DISTINCT srr.identity_id FROM storage_root_roles srr WHERE srr.root_id = :storage_root_id AND LOWER(srr"""
    return db.execute(
        text(
                    """
                    SELECT DISTINCT srr.identity_id
                    FROM storage_root_roles srr
                    WHERE srr.root_id = :storage_root_id
                      AND LOWER(srr.role) = 'guardian'
                    """
                ),
        params,
    )


def root_zone_name_1(db: Session, params: Any) -> Any:
    """SELECT name FROM zones WHERE id = :id"""
    return db.execute(
        text("SELECT name FROM zones WHERE id = :id"),
        params,
    )


def assert_root_on_endpoint_host_1(db: Session, params: Any) -> Any:
    """SELECT host FROM storage_endpoints WHERE id = :id"""
    return db.execute(
        text("SELECT host FROM storage_endpoints WHERE id = :id"),
        params,
    )


def resolve_parent_storage_root_id_1(db: Session, params: Any) -> Any:
    """SELECT id, normalized_root_path, root_path FROM storage_roots WHERE storage_endpoint_id = :storage_endpoint_id"""
    return db.execute(
        text(
                    """
                    SELECT id, normalized_root_path, root_path
                    FROM storage_roots
                    WHERE storage_endpoint_id = :storage_endpoint_id
                      AND (:exclude_root_id IS NULL OR id <> :exclude_root_id)
                      AND deleted_at IS NULL
                    """
                ),
        params,
    )


def assert_unique_storage_root_path_1(db: Session, params: Any) -> Any:
    """SELECT id FROM storage_roots WHERE storage_endpoint_id = :storage_endpoint_id AND COALESCE(NULLIF(normalized_r"""
    return db.execute(
        text(
                    """
                    SELECT id
                    FROM storage_roots
                    WHERE storage_endpoint_id = :storage_endpoint_id
                      AND COALESCE(NULLIF(normalized_root_path, ''), LOWER(TRIM(TRAILING '/' FROM REPLACE(root_path, '\\\\', '/')))) = :normalized_root_path
                      AND (:exclude_root_id IS NULL OR id <> :exclude_root_id)
                      AND deleted_at IS NULL
                    LIMIT 1
                    """
                ),
        params,
    )


def child_storage_roots_1(db: Session, params: Any) -> Any:
    """SELECT id, name, root_path, storage_endpoint_id FROM storage_roots WHERE parent_storage_root_id = :parent_stor"""
    return db.execute(
        text(
                        """
                        SELECT id, name, root_path, storage_endpoint_id
                        FROM storage_roots
                        WHERE parent_storage_root_id = :parent_storage_root_id
                          AND deleted_at IS NULL
                        ORDER BY name, id
                        """
                    ),
        params,
    )


def discovered_snapshots_1(db: Session) -> Any:
    """SELECT storage_endpoint_id, root_path FROM storage_roots"""
    return db.execute(
        text("SELECT storage_endpoint_id, root_path FROM storage_roots"),
    )


def get_storage_roots_exposure_1(db: Session) -> Any:
    """SELECT id AS storage_root_id FROM storage_roots WHERE deleted_at IS NULL"""
    return db.execute(
        text("SELECT id AS storage_root_id FROM storage_roots WHERE deleted_at IS NULL"),
    )


def check_bulk_guardians_1(db: Session, params: Any) -> Any:
    """SELECT identity_source_id FROM storage_endpoints WHERE id = :id"""
    return db.execute(
        text("SELECT identity_source_id FROM storage_endpoints WHERE id = :id"),
        params,
    )


def explain_root_access_1(db: Session, params: Any) -> Any:
    """SELECT display_name FROM directory_users WHERE LOWER(username) = :u LIMIT 1"""
    return db.execute(
        text("SELECT display_name FROM directory_users WHERE LOWER(username) = :u LIMIT 1"),
        params,
    )


def accept_acl_gap_1(db: Session, params: Any) -> Any:
    """INSERT INTO storage_root_acl_exceptions (storage_root_id, principal, note, accepted_by) VALUES (:root, :princi"""
    return db.execute(
        text(
                    """
                    INSERT INTO storage_root_acl_exceptions (storage_root_id, principal, note, accepted_by)
                    VALUES (:root, :principal, :note, :by)
                    ON DUPLICATE KEY UPDATE note = VALUES(note), accepted_by = VALUES(accepted_by), accepted_at = CURRENT_TIMESTAMP
                    """
                ),
        params,
    )


def reopen_acl_gap_1(db: Session, params: Any) -> Any:
    """DELETE FROM storage_root_acl_exceptions WHERE storage_root_id = :root AND principal = :principal"""
    return db.execute(
        text("DELETE FROM storage_root_acl_exceptions WHERE storage_root_id = :root AND principal = :principal"),
        params,
    )


def repair_root_acl_1(db: Session, params: Any) -> Any:
    """SELECT access_level_code, group_name FROM storage_root_access_profiles WHERE storage_root_id = :root_id AND st"""
    return db.execute(
        text(
                        """
                        SELECT access_level_code, group_name
                        FROM storage_root_access_profiles
                        WHERE storage_root_id = :root_id AND status = 'SUCCEEDED' AND group_name IS NOT NULL
                        """
                    ),
        params,
    )


def create_root_subfolder_1(db: Session, params: Any) -> Any:
    """INSERT INTO storage_root_roles (root_id, identity_id, role, assigned_by, assigned_at) SELECT :child, identity_"""
    return db.execute(
        text(
                            """
                            INSERT INTO storage_root_roles (root_id, identity_id, role, assigned_by, assigned_at)
                            SELECT :child, identity_id, role, :actor, CURRENT_TIMESTAMP FROM storage_root_roles WHERE root_id = :parent
                            """
                        ),
        params,
    )


def create_root_subfolder_2(db: Session, params: Any) -> Any:
    """INSERT INTO storage_root_tags (storage_root_id, tag_id, created_at, updated_at) SELECT :child, tag_id, CURRENT"""
    return db.execute(
        text(
                            """
                            INSERT INTO storage_root_tags (storage_root_id, tag_id, created_at, updated_at)
                            SELECT :child, tag_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                            FROM storage_root_tags WHERE storage_root_id = :parent AND deleted_at IS NULL
                            """
                        ),
        params,
    )
