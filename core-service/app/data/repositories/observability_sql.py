"""SQL of the routes of api/observability.py, moved out of them unchanged: each function runs the statement the route
ran and returns the same result (the routes hold no SQL)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def health_1(db: Session) -> Any:
    """SELECT next_run_at FROM infra_schedules WHERE task = 'health_check'"""
    return db.execute(
        text("SELECT next_run_at FROM infra_schedules WHERE task = 'health_check'"),
    )


def alerts_1(db: Session) -> Any:
    """SELECT ga.id, ga.alert_type, ga.severity, ga.status, ga.title, ga.message, ga.storage_root_id, ga.storage_endp"""
    return db.execute(
        text(
                        """
                        SELECT ga.id, ga.alert_type, ga.severity, ga.status, ga.title, ga.message, ga.storage_root_id,
                               ga.storage_endpoint_id, ga.identity_source_id, ga.first_seen_at, ga.last_seen_at,
                               COALESCE(sr.name, se.name, s.name) AS scope_name
                        FROM governance_alerts ga
                        LEFT JOIN storage_roots sr ON sr.id = ga.storage_root_id
                        LEFT JOIN storage_endpoints se ON se.id = ga.storage_endpoint_id
                        LEFT JOIN identity_sources s ON s.id = ga.identity_source_id
                        WHERE ga.status IN ('open', 'acknowledged')
                        """
                    ),
    )


def alerts_2(db: Session, params: Any) -> Any:
    """SELECT COUNT(*) FROM governance_alerts WHERE severity IN ('critical', 'high') AND first_seen_at >= UTC_TIMESTA"""
    return db.execute(
        text(
                    """
                    SELECT COUNT(*) FROM governance_alerts
                    WHERE severity IN ('critical', 'high') AND first_seen_at >= UTC_TIMESTAMP() - INTERVAL :hours HOUR
                    """
                ),
        params,
    )


def jobs_1(db: Session, params: Any) -> Any:
    """SELECT COUNT(*) AS total, SUM(UPPER(status) = 'FAILED') AS failed FROM provisioning_jobs WHERE created_at >= N"""
    return db.execute(
        text(
                    """
                    SELECT
                      COUNT(*) AS total,
                      SUM(UPPER(status) = 'FAILED') AS failed
                    FROM provisioning_jobs
                    WHERE created_at >= NOW() - INTERVAL :hours HOUR
                    """
                ),
        params,
    )


def jobs_2(db: Session) -> Any:
    """SELECT id, status, payload_json, TIMESTAMPDIFF(SECOND, created_at, COALESCE(started_at, UTC_TIMESTAMP())) AS w"""
    return db.execute(
        text(
                    """
                    SELECT id, status, payload_json,
                           TIMESTAMPDIFF(SECOND, created_at, COALESCE(started_at, UTC_TIMESTAMP())) AS wait_seconds,
                           CASE WHEN started_at IS NULL THEN NULL ELSE TIMESTAMPDIFF(SECOND, started_at, UTC_TIMESTAMP()) END AS run_seconds
                    FROM provisioning_jobs WHERE status IN ('CREATED', 'QUEUED', 'RETRYING', 'RUNNING')
                    """
                ),
    )


def jobs_3(db: Session, params: Any) -> Any:
    """(SELECT id, job_type, action, status, error_code, error_message, identity_source_id, storage_root_access_profi"""
    return db.execute(
        text(
                        """
                        (SELECT id, job_type, action, status, error_code, error_message, identity_source_id,
                                storage_root_access_profile_id, updated_at
                         FROM provisioning_jobs
                         WHERE UPPER(status) = 'FAILED' AND created_at >= NOW() - INTERVAL :hours HOUR
                         ORDER BY updated_at DESC LIMIT 4)
                        UNION ALL
                        (SELECT id, job_type, action, status, error_code, error_message, identity_source_id,
                                storage_root_access_profile_id, updated_at
                         FROM provisioning_jobs
                         WHERE UPPER(status) IN ('QUEUED', 'RUNNING', 'RETRYING')
                         ORDER BY updated_at DESC LIMIT 3)
                        """
                    ),
        params,
    )


def get_badge_1(db: Session) -> Any:
    """SELECT COUNT(*) FROM governance_alerts WHERE status = 'open' AND severity IN ('critical', 'high')"""
    return db.execute(
        text("SELECT COUNT(*) FROM governance_alerts WHERE status = 'open' AND severity IN ('critical', 'high')"),
    )
