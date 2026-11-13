"""SQL of the routes of api/access_requests.py, moved out of them unchanged: each function runs the statement the route
ran and returns the same result (the routes hold no SQL)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def resolve_implicit_governed_group_1(db: Session, params: Any) -> Any:
    """SELECT sr.id AS storage_root_id, se.identity_source_id FROM storage_roots sr JOIN storage_endpoints se ON se.i"""
    return db.execute(
        text(
                    """
                    SELECT sr.id AS storage_root_id, se.identity_source_id
                    FROM storage_roots sr
                    JOIN storage_endpoints se ON se.id = sr.storage_endpoint_id
                    WHERE sr.id = :storage_root_id
                    LIMIT 1
                    """
                ),
        params,
    )


def granted_level_from_requests_1(db: Session, params: Any) -> Any:
    """SELECT ar.requester_identity_id, ar.requested_principal_json, ari.permission FROM access_requests ar JOIN acce"""
    return db.execute(
        text(
                    """
                    SELECT ar.requester_identity_id, ar.requested_principal_json, ari.permission
                    FROM access_requests ar
                    JOIN access_request_items ari ON ari.access_request_id = ar.id
                    WHERE LOWER(COALESCE(ar.status, '')) IN ('approved', 'executed')
                      AND ar.revoked_at IS NULL
                      AND LOWER(COALESCE(ari.target_type, '')) = 'storage_root'
                      AND ari.target_id = :storage_root_id
                      AND (ari.expires_at IS NULL OR ari.expires_at > UTC_TIMESTAMP())
                    """
                ),
        params,
    )


def find_open_request_for_principal_1(db: Session, params: Any) -> Any:
    """SELECT ar.id, ar.code, ar.requester_identity_id, ar.requested_principal_json FROM access_requests ar JOIN acce"""
    return db.execute(
        text(
                    """
                    SELECT
                      ar.id,
                      ar.code,
                      ar.requester_identity_id,
                      ar.requested_principal_json
                    FROM access_requests ar
                    JOIN access_request_items ari ON ari.access_request_id = ar.id
                    WHERE LOWER(COALESCE(ar.status, '')) = 'pending'
                      AND LOWER(COALESCE(ari.target_type, '')) = 'storage_root'
                      AND ari.target_id = :storage_root_id
                    ORDER BY ar.id DESC
                    """
                ),
        params,
    )


def storage_endpoint_inactive_1(db: Session, params: Any) -> Any:
    """SELECT se.is_active, se.status FROM storage_roots sr JOIN storage_endpoints se ON se.id = sr.storage_endpoint_"""
    return db.execute(
        text(
                    "SELECT se.is_active, se.status FROM storage_roots sr JOIN storage_endpoints se ON se.id = sr.storage_endpoint_id "
                    "WHERE sr.id = :root_id"
                ),
        params,
    )


def resolve_principal_from_identity_id_1(db: Session, params: Any) -> Any:
    """SELECT COALESCE(NULLIF(TRIM(du.dn), ''), NULLIF(TRIM(du.external_id), ''), NULLIF(TRIM(i.external_id), '')) AS"""
    return db.execute(
        text(
                    """
                    SELECT
                      COALESCE(NULLIF(TRIM(du.dn), ''), NULLIF(TRIM(du.external_id), ''), NULLIF(TRIM(i.external_id), '')) AS principal_dn,
                      COALESCE(
                        NULLIF(TRIM(du.username), ''),
                        NULLIF(TRIM(du.upn), ''),
                        NULLIF(TRIM(i.username), ''),
                        NULLIF(TRIM(i.email), '')
                      ) AS principal_username,
                      COALESCE(
                        NULLIF(TRIM(i.display_name), ''),
                        NULLIF(TRIM(du.display_name), ''),
                        NULLIF(TRIM(i.username), ''),
                        NULLIF(TRIM(du.username), ''),
                        CAST(i.id AS CHAR)
                      ) AS principal_display
                    FROM identities i
                    LEFT JOIN identity_bindings ib
                      ON ib.identity_id = i.id
                     AND ib.deleted_at IS NULL
                    LEFT JOIN directory_users du
                      ON du.id = ib.directory_user_id
                    WHERE i.id = :id
                    ORDER BY ib.id DESC
                    LIMIT 1
                    """
                ),
        params,
    )


def insert_item_execution_1(db: Session, params: Any) -> Any:
    """SELECT id FROM access_request_item_executions WHERE access_request_id = :access_request_id AND ( (:access_requ"""
    return db.execute(
        text(
                        """
                        SELECT id
                        FROM access_request_item_executions
                        WHERE access_request_id = :access_request_id
                          AND (
                            (:access_request_item_id IS NULL AND access_request_item_id IS NULL)
                            OR access_request_item_id = :access_request_item_id
                          )
                          AND UPPER(COALESCE(status, '')) = :status
                          AND JSON_UNQUOTE(JSON_EXTRACT(requested_payload_json, '$.correlation_id')) = :correlation_id
                        ORDER BY id DESC
                        LIMIT 1
                        """
                    ),
        params,
    )


def insert_item_execution_2(db: Session, params: Any) -> Any:
    """INSERT INTO access_request_item_executions ( access_request_id, access_request_item_id, status, error_message,"""
    return db.execute(
        text(
                    """
                    INSERT INTO access_request_item_executions (
                      access_request_id,
                      access_request_item_id,
                      status,
                      error_message,
                      requested_payload_json,
                      result_json,
                      started_at,
                      finished_at,
                      created_at,
                      updated_at
                    ) VALUES (
                      :access_request_id,
                      :access_request_item_id,
                      :status,
                      :error_message,
                      :requested_payload_json,
                      :result_json,
                      NOW(6),
                      NOW(6),
                      NOW(6),
                      NOW(6)
                    )
                    """
                ),
        params,
    )


def build_access_request_provisioning_plan_1(db: Session, params: Any) -> Any:
    """SELECT id, requester_identity_id, requested_principal_json FROM access_requests WHERE id = :id LIMIT 1"""
    return db.execute(
        text(
                    """
                    SELECT id, requester_identity_id, requested_principal_json
                    FROM access_requests
                    WHERE id = :id
                    LIMIT 1
                    """
                ),
        params,
    )


def build_access_request_provisioning_plan_2(db: Session, params: Any) -> Any:
    """SELECT id, target_type, target_id, permission FROM access_request_items WHERE access_request_id = :id ORDER BY"""
    return db.execute(
        text(
                    """
                    SELECT id, target_type, target_id, permission
                    FROM access_request_items
                    WHERE access_request_id = :id
                    ORDER BY id ASC
                    """
                ),
        params,
    )


def summarize_visibility_sources_for_request_1(db: Session, params: Any) -> Any:
    """SELECT result_json FROM access_request_item_executions WHERE access_request_id = :id AND UPPER(COALESCE(status"""
    return db.execute(
        text(
                    """
                    SELECT result_json
                    FROM access_request_item_executions
                    WHERE access_request_id = :id
                      AND UPPER(COALESCE(status, '')) = 'DONE'
                    ORDER BY id DESC
                    """
                ),
        params,
    )


def get_access_request_details_1(db: Session, params: Any) -> Any:
    """SELECT requester_identity_id, status, decision_comment, decided_at FROM access_requests WHERE id = :id"""
    return db.execute(
        text("SELECT requester_identity_id, status, decision_comment, decided_at FROM access_requests WHERE id = :id"),
        params,
    )


def get_access_request_approval_preview_1(db: Session) -> Any:
    """SELECT status FROM infra_workers WHERE is_enabled = 1"""
    return db.execute(
        text("SELECT status FROM infra_workers WHERE is_enabled = 1"),
    )


def get_access_request_approval_preview_2(db: Session, params: Any) -> Any:
    """SELECT name, capabilities, write_enabled, is_active FROM identity_sources WHERE id = :id"""
    return db.execute(
        text("SELECT name, capabilities, write_enabled, is_active FROM identity_sources WHERE id = :id"),
        params,
    )


def forget_direct_membership_1(db: Session, params: Any) -> Any:
    """SELECT id, identity_source_id, external_id, dn, name FROM directory_groups WHERE deleted_at IS NULL AND (:sour"""
    return db.execute(
        text(
                    """
                    SELECT id, identity_source_id, external_id, dn, name
                    FROM directory_groups
                    WHERE deleted_at IS NULL
                      AND (:source_id IS NULL OR identity_source_id = :source_id)
                      AND (LOWER(name) = LOWER(:group_ref) OR LOWER(dn) = LOWER(:group_ref))
                    ORDER BY id DESC
                    LIMIT 1
                    """
                ),
        params,
    )


def forget_direct_membership_2(db: Session, params: Any) -> Any:
    """SELECT id, external_id, dn FROM directory_users WHERE identity_source_id = :source_id AND (LOWER(dn) = LOWER(:"""
    return db.execute(
        text(
                    """
                    SELECT id, external_id, dn
                    FROM directory_users
                    WHERE identity_source_id = :source_id
                      AND (LOWER(dn) = LOWER(:dn) OR LOWER(username) = LOWER(:username))
                    ORDER BY LOWER(dn) = LOWER(:dn) DESC
                    LIMIT 1
                    """
                ),
        params,
    )


def forget_direct_membership_3(db: Session, params: Any) -> Any:
    """DELETE FROM directory_effective_memberships WHERE directory_group_id = :group_id AND directory_user_id = :user"""
    return db.execute(
        text(
                    """
                    DELETE FROM directory_effective_memberships
                    WHERE directory_group_id = :group_id AND directory_user_id = :user_id AND depth = 0
                    """
                ),
        params,
    )


def forget_direct_membership_4(db: Session, params: Any) -> Any:
    """DELETE FROM directory_group_members WHERE group_id = :group_id AND directory_user_id = :user_id"""
    return db.execute(
        text("DELETE FROM directory_group_members WHERE group_id = :group_id AND directory_user_id = :user_id"),
        params,
    )


def forget_direct_membership_5(db: Session, params: Any) -> Any:
    """DELETE FROM directory_snapshot_memberships WHERE snapshot_id = :snapshot_id AND LOWER(group_external_id) IN (L"""
    return db.execute(
        text(
                        """
                        DELETE FROM directory_snapshot_memberships
                        WHERE snapshot_id = :snapshot_id
                          AND LOWER(group_external_id) IN (LOWER(:group_external_id), LOWER(:group_dn), LOWER(:group_name))
                          AND LOWER(member_external_id) IN (LOWER(:member_external_id), LOWER(:member_dn))
                        """
                    ),
        params,
    )


def other_active_request_for_level_1(db: Session, params: Any) -> Any:
    """SELECT requester_identity_id, requested_principal_json FROM access_requests WHERE id = :id"""
    return db.execute(
        text("SELECT requester_identity_id, requested_principal_json FROM access_requests WHERE id = :id"),
        params,
    )


def other_active_request_for_level_2(db: Session, params: Any) -> Any:
    """SELECT ar.id, ar.code, ar.requester_identity_id, ar.requested_principal_json, ari.permission FROM access_reque"""
    return db.execute(
        text(
                    """
                    SELECT ar.id, ar.code, ar.requester_identity_id, ar.requested_principal_json, ari.permission
                    FROM access_requests ar
                    JOIN access_request_items ari ON ari.access_request_id = ar.id
                    WHERE ar.id <> :id
                      AND LOWER(COALESCE(ar.status, '')) IN ('approved', 'executed')
                      AND ar.revoked_at IS NULL
                      AND LOWER(COALESCE(ari.target_type, '')) = 'storage_root'
                      AND ari.target_id = :root_id
                      AND (ari.expires_at IS NULL OR ari.expires_at > UTC_TIMESTAMP())
                    """
                ),
        params,
    )


def request_event_labels_1(db: Session, params: Any) -> Any:
    """SELECT ar.requested_principal_json, ari.target_type, ari.target_id, ari.permission FROM access_requests ar JOI"""
    return db.execute(
        text(
                        """
                        SELECT ar.requested_principal_json, ari.target_type, ari.target_id, ari.permission
                        FROM access_requests ar
                        JOIN access_request_items ari ON ari.access_request_id = ar.id
                        WHERE ar.id = :id
                        LIMIT 1
                        """
                    ),
        params,
    )


def created_event_labels_1(db: Session, params: Any) -> Any:
    """SELECT name FROM storage_roots WHERE id = :id"""
    return db.execute(
        text("SELECT name FROM storage_roots WHERE id = :id"),
        params,
    )


def change_access_request_permission_1(db: Session, params: Any) -> Any:
    """SELECT status, requester_identity_id, requested_principal_json FROM access_requests WHERE id = :id"""
    return db.execute(
        text("SELECT status, requester_identity_id, requested_principal_json FROM access_requests WHERE id = :id"),
        params,
    )


def change_access_request_permission_2(db: Session, params: Any) -> Any:
    """SELECT id, target_id, permission FROM access_request_items WHERE access_request_id = :id AND LOWER(COALESCE(ta"""
    return db.execute(
        text(
                    """
                    SELECT id, target_id, permission FROM access_request_items
                    WHERE access_request_id = :id AND LOWER(COALESCE(target_type, '')) = 'storage_root'
                    """
                ),
        params,
    )


def change_access_request_permission_3(db: Session, params: Any) -> Any:
    """UPDATE access_request_items SET original_permission = COALESCE(original_permission, permission), permission = """
    return db.execute(
        text(
                    """
                    UPDATE access_request_items
                    SET original_permission = COALESCE(original_permission, permission),
                        permission = :permission,
                        permission_changed_by = :actor_id,
                        permission_changed_by_display = :actor_display,
                        permission_changed_at = UTC_TIMESTAMP(),
                        permission_change_reason = :reason
                    WHERE access_request_id = :id AND LOWER(COALESCE(target_type, '')) = 'storage_root'
                    """
                ),
        params,
    )


def cancel_access_request_1(db: Session, params: Any) -> Any:
    """SELECT id, requester_identity_id, status FROM access_requests WHERE id = :id"""
    return db.execute(
        text("SELECT id, requester_identity_id, status FROM access_requests WHERE id = :id"),
        params,
    )


def cancel_access_request_2(db: Session, params: Any) -> Any:
    """UPDATE access_requests SET status = 'cancelled', decided_at = :now, updated_at = :now WHERE id = :id AND statu"""
    return db.execute(
        text("UPDATE access_requests SET status = 'cancelled', decided_at = :now, updated_at = :now WHERE id = :id AND status = 'pending'"),
        params,
    )


def extend_access_request_1(db: Session, params: Any) -> Any:
    """SELECT ar.status, ar.revoked_at, MIN(ari.expires_at) AS expires_at, COUNT(ari.id) AS items, SUM(ari.expires_at"""
    return db.execute(
        text(
                    """
                    SELECT ar.status, ar.revoked_at, MIN(ari.expires_at) AS expires_at, COUNT(ari.id) AS items,
                           SUM(ari.expires_at IS NULL) AS permanent
                    FROM access_requests ar JOIN access_request_items ari ON ari.access_request_id = ar.id
                    WHERE ar.id = :id GROUP BY ar.status, ar.revoked_at
                    """
                ),
        params,
    )


def extend_access_request_2(db: Session, params: Any) -> Any:
    """UPDATE access_request_items SET expires_at = GREATEST(expires_at, UTC_TIMESTAMP()) + INTERVAL :days DAY WHERE """
    return db.execute(
        text(
                    """
                    UPDATE access_request_items
                    SET expires_at = GREATEST(expires_at, UTC_TIMESTAMP()) + INTERVAL :days DAY
                    WHERE access_request_id = :id AND expires_at IS NOT NULL
                    """
                ),
        params,
    )


def extend_access_request_3(db: Session, params: Any) -> Any:
    """SELECT MAX(expires_at) FROM access_request_items WHERE access_request_id = :id"""
    return db.execute(
        text("SELECT MAX(expires_at) FROM access_request_items WHERE access_request_id = :id"),
        params,
    )


def bulk_decision_1(db: Session, params: Any) -> Any:
    """UPDATE access_requests SET status = 'revoked', revoked_at = COALESCE(revoked_at, :now), updated_at = CURRENT_T"""
    return db.execute(
        text(
                                """
                                UPDATE access_requests
                                SET status = 'revoked',
                                    revoked_at = COALESCE(revoked_at, :now),
                                    updated_at = CURRENT_TIMESTAMP
                                WHERE id = :id
                                """
                            ),
        params,
    )
