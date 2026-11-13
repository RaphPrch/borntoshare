"""SQL of the routes of api/infrastructure.py, moved out of them unchanged: each function runs the statement the route
ran and returns the same result (the routes hold no SQL)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def create_worker_1(db: Session, params: Any) -> Any:
    """INSERT INTO infra_workers (name, host, port, use_tls, verify_tls, is_enabled) VALUES (:name, :host, :port, :us"""
    return db.execute(
        text(
                        """
                        INSERT INTO infra_workers (name, host, port, use_tls, verify_tls, is_enabled)
                        VALUES (:name, :host, :port, :use_tls, :verify_tls, :is_enabled)
                        """
                    ),
        params,
    )


def delete_worker_1(db: Session, params: Any) -> Any:
    """DELETE FROM infra_workers WHERE id = :id"""
    return db.execute(
        text("DELETE FROM infra_workers WHERE id = :id"),
        params,
    )


def delete_worker_2(db: Session, params: Any) -> Any:
    """DELETE FROM infra_component_status WHERE component = :c"""
    return db.execute(
        text("DELETE FROM infra_component_status WHERE component = :c"),
        params,
    )


def with_job_outcome_1(db: Session, params: Any) -> Any:
    """SELECT UPPER(status) AS status, COUNT(*) AS n FROM provisioning_jobs WHERE created_at >= :since AND (job_type """
    return db.execute(
        text(
                    """
                    SELECT UPPER(status) AS status, COUNT(*) AS n
                    FROM provisioning_jobs
                    WHERE created_at >= :since
                      AND (job_type = 'DIRECTORY_SNAPSHOT'
                           OR JSON_VALUE(payload_json, '$.payload.context.origin') = 'data_sync')
                    GROUP BY UPPER(status)
                    """
                ),
        params,
    )


def schedules_1(db: Session) -> Any:
    """SELECT * FROM infra_schedules ORDER BY task"""
    return db.execute(
        text("SELECT * FROM infra_schedules ORDER BY task"),
    )


def list_late_schedules_1(db: Session) -> Any:
    """SELECT task, interval_minutes, last_run_at, last_status, TIMESTAMPDIFF(MINUTE, last_run_at, UTC_TIMESTAMP()) A"""
    return db.execute(
        text(
                    """
                    SELECT task, interval_minutes, last_run_at, last_status,
                      TIMESTAMPDIFF(MINUTE, last_run_at, UTC_TIMESTAMP()) AS late_minutes
                    FROM infra_schedules
                    WHERE is_enabled = 1 AND last_run_at IS NOT NULL
                      AND last_run_at < UTC_TIMESTAMP() - INTERVAL (2 * interval_minutes) MINUTE
                    ORDER BY late_minutes DESC
                    """
                ),
    )


def run_schedule_1(db: Session, params: Any) -> Any:
    """SELECT last_status = 'running' AND last_run_at > UTC_TIMESTAMP() - INTERVAL 30 MINUTE FROM infra_schedules WHE"""
    return db.execute(
        text(
                    """
                    SELECT last_status = 'running' AND last_run_at > UTC_TIMESTAMP() - INTERVAL 30 MINUTE
                    FROM infra_schedules WHERE task = :task
                    """
                ),
        params,
    )


def services_1(db: Session) -> Any:
    """SELECT * FROM infra_services ORDER BY is_builtin DESC, label"""
    return db.execute(
        text("SELECT * FROM infra_services ORDER BY is_builtin DESC, label"),
    )


def create_service_1(db: Session, params: Any) -> Any:
    """INSERT INTO infra_services (component_key, label, category, check_kind, target, is_enabled) VALUES (:key, :lab"""
    return db.execute(
        text(
                        """
                        INSERT INTO infra_services (component_key, label, category, check_kind, target, is_enabled)
                        VALUES (:key, :label, :category, :check_kind, :target, :is_enabled)
                        """
                    ),
        params,
    )


def update_service_1(db: Session, params: Any) -> Any:
    """SELECT * FROM infra_services WHERE id = :id"""
    return db.execute(
        text("SELECT * FROM infra_services WHERE id = :id"),
        params,
    )


def update_service_2(db: Session, params: Any) -> Any:
    """UPDATE infra_services SET label = :label, category = :category, check_kind = :check_kind, target = :target, is"""
    return db.execute(
        text("UPDATE infra_services SET label = :label, category = :category, check_kind = :check_kind, target = :target, is_enabled = :is_enabled WHERE id = :id"),
        params,
    )


def update_service_3(db: Session, params: Any) -> Any:
    """DELETE FROM infra_component_status WHERE component = :c"""
    return db.execute(
        text("DELETE FROM infra_component_status WHERE component = :c"),
        params,
    )


def delete_service_1(db: Session, params: Any) -> Any:
    """SELECT * FROM infra_services WHERE id = :id"""
    return db.execute(
        text("SELECT * FROM infra_services WHERE id = :id"),
        params,
    )


def delete_service_2(db: Session, params: Any) -> Any:
    """DELETE FROM infra_services WHERE id = :id"""
    return db.execute(
        text("DELETE FROM infra_services WHERE id = :id"),
        params,
    )


def delete_service_3(db: Session, params: Any) -> Any:
    """DELETE FROM infra_component_status WHERE component = :c"""
    return db.execute(
        text("DELETE FROM infra_component_status WHERE component = :c"),
        params,
    )


def check_roles_1(db: Session) -> Any:
    """SELECT code FROM roles"""
    return db.execute(
        text("SELECT code FROM roles"),
    )


def list_sso_providers_1(db: Session) -> Any:
    """SELECT code, label FROM roles ORDER BY id"""
    return db.execute(
        text("SELECT code, label FROM roles ORDER BY id"),
    )


def delete_sso_provider_1(db: Session, params: Any) -> Any:
    """DELETE FROM infra_component_status WHERE component = :c"""
    return db.execute(
        text("DELETE FROM infra_component_status WHERE component = :c"),
        params,
    )


def record_sso_status_1(db: Session, params: Any) -> Any:
    """UPDATE sso_providers SET status = :status, last_message = :message, last_check_at = UTC_TIMESTAMP() WHERE id ="""
    return db.execute(
        text("UPDATE sso_providers SET status = :status, last_message = :message, last_check_at = UTC_TIMESTAMP() WHERE id = :id"),
        params,
    )
