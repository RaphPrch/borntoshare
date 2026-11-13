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


def is_current_folder_job_1(db: Session, params: Any, *, table: Any) -> Any:
    """WHERE storage_root_id = :id"""
    return db.execute(
        text(f"SELECT job_id FROM {table} WHERE storage_root_id = :id"),
        params,
    )


def get_storage_root_provisioning_context_1(db: Session, params: Any, *, effective_group_ou_sql: Any) -> Any:
    """SELECT sr.id AS storage_root_id, sr.name AS storage_root_name, sr.root_path, se.id AS storage_endpoint_id, se."""
    return db.execute(
        text(
                    f"""
                    SELECT
                      sr.id AS storage_root_id,
                      sr.name AS storage_root_name,
                      sr.root_path,
                      se.id AS storage_endpoint_id,
                      se.zone_id,
                      se.host,
                      se.name AS endpoint_name,
                      se.endpoint_type,
                      se.port AS endpoint_port,
                      se.protocol AS endpoint_protocol,
                      se.sub_ou_dn,
                      se.bind_dn AS endpoint_bind_dn,
                      se.bind_password_ref AS endpoint_bind_password_ref,
                      se.identity_source_id,
                      UPPER(COALESCE(NULLIF(ids.type, ''), 'ad')) AS identity_source_kind,
                      ids.host AS identity_source_host,
                      ids.port AS identity_source_port,
                      ids.protocol AS identity_source_protocol,
                      ids.bind_dn AS identity_source_bind_dn,
                      ids.bind_password_ref AS identity_source_bind_password_ref,
                      ids.base_dn AS identity_source_base_dn,
                      ids.domain_name,
                      CASE
                        WHEN COALESCE(ids.write_enabled, 0) = 1 THEN 1
                        WHEN COALESCE(
                          NULLIF(ids.bind_password_ref, ''),
                          NULLIF(se.bind_password_ref, '')
                        ) IS NOT NULL THEN 1
                        ELSE 0
                      END AS write_enabled,
                      ids.default_group_ou_dn,
                      zpp.base_ou_dn AS zone_default_group_ou_dn,
                      {effective_group_ou_sql} AS effective_group_ou_dn
                    FROM storage_roots sr
                    JOIN storage_endpoints se ON se.id = sr.storage_endpoint_id
                    LEFT JOIN zone_provisioning_policy zpp ON zpp.zone_id = se.zone_id
                    LEFT JOIN identity_sources ids ON ids.id = se.identity_source_id
                    WHERE sr.id = :id
                    LIMIT 1
                    """
                ),
        params,
    )


def list_provisioning_jobs_1(db: Session, params: Any, *, conds: Any) -> Any:
    """SELECT pj.id, pj.correlation_id, pj.job_type, pj.action, UPPER(COALESCE(pj.status, 'QUEUED')) AS status, pj.st"""
    return db.execute(
        text(
                    f"""
                    SELECT
                      pj.id,
                      pj.correlation_id,
                      pj.job_type,
                      pj.action,
                      UPPER(COALESCE(pj.status, 'QUEUED')) AS status,
                      pj.storage_root_access_profile_id,
                      pj.identity_source_id,
                      pj.payload_json,
                      pj.result_json,
                      pj.metrics_json,
                      pj.error_json,
                      pj.error_code,
                      pj.error_message,
                      pj.started_at,
                      pj.finished_at,
                      pj.created_at,
                      pj.updated_at,
                      TIMESTAMPDIFF(SECOND, pj.created_at, UTC_TIMESTAMP()) AS queue_age_seconds,
                      TIMESTAMPDIFF(SECOND, pj.created_at, COALESCE(pj.started_at, pj.finished_at, UTC_TIMESTAMP())) AS wait_seconds,
                      CASE WHEN pj.started_at IS NULL THEN NULL
                           ELSE TIMESTAMPDIFF(SECOND, pj.started_at, COALESCE(pj.finished_at, UTC_TIMESTAMP())) END AS run_seconds,
                      CAST(
                        COALESCE(
                          JSON_UNQUOTE(JSON_EXTRACT(pj.metrics_json, '$.watchdog_republish_count')),
                          '0'
                        ) AS UNSIGNED
                      ) AS watchdog_republish_count
                    FROM provisioning_jobs pj
                    WHERE {' AND '.join(conds)}
                    ORDER BY pj.updated_at DESC, pj.id DESC
                    LIMIT :lim
                    """
                ),
        params,
    )
