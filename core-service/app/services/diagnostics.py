"""Diagnostic of the installation (Observability › Health › Diagnostic): each check gives a result, a severity and
the values of its explanation; the sentences (what it means, what to do) are written by the interface, in its
languages. Read only, never a secret: a secret is reported as present or absent, never shown.

Every check comes from what the platform already measures (health check of the components, workers, jobs, database
account) or measures here (disk, configuration); none is a fake indicator: without data a check says « unknown ».
"""
from __future__ import annotations

import os
import shutil
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.logging import get_logger

logger = get_logger("core.diagnostics")

OK, WARNING, ERROR, UNKNOWN = "ok", "warning", "error", "unknown"
DISK_WARNING_PERCENT = 85
DISK_ERROR_PERCENT = 95
INTERNAL_TOKEN_MIN_LENGTH = 32


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _check(code: str, area: str, result: str, severity: str, **values: Any) -> dict[str, Any]:
    return {"code": code, "area": area, "result": result, "severity": severity if result != OK else "info", "values": values}


def _guarded(code: str, area: str, severity: str, run) -> list[dict[str, Any]]:
    """A check that cannot run says so (unknown, with the reason in the log), instead of failing the whole report."""
    try:
        out = run()
        return out if isinstance(out, list) else [out]
    except Exception:
        logger.warning("DIAGNOSTIC_CHECK_FAILED", extra={"check": code}, exc_info=True)
        return [_check(code, area, UNKNOWN, severity)]


# ---- configuration ------------------------------------------------------------------------------------------------

def _internal_token() -> dict[str, Any]:
    length = len((os.getenv("INTERNAL_TOKEN") or "").strip())
    return _check("config.internal_token", "configuration", OK if length >= INTERNAL_TOKEN_MIN_LENGTH else ERROR, "high",
                  length=length, minimum=INTERNAL_TOKEN_MIN_LENGTH)


def _master_key() -> dict[str, Any]:
    from app.services.secret_store import SecretError, master_key

    try:
        master_key()
        return _check("config.master_key", "configuration", OK, "critical")
    except SecretError:
        return _check("config.master_key", "configuration", ERROR, "critical")


def _missing_secrets(db: Session) -> dict[str, Any]:
    from app.services.secret_store import missing_secrets

    missing = missing_secrets(db)
    return _check("secrets.missing", "configuration", ERROR if missing else OK, "high",
                  count=len(missing), names=[str(item["name"]) for item in missing[:10]])


# ---- data ---------------------------------------------------------------------------------------------------------

def _live_connections() -> list[dict[str, Any]]:
    from app.services.infrastructure_service import _core_side_checks

    codes = {"database": ("database.application", "critical"), "logging_database": ("database.audit", "critical"),
             "job_queue": ("queue.redis", "critical")}
    out = []
    for item in _core_side_checks():
        code, severity = codes.get(str(item["component"]), (f"component.{item['component']}", "high"))
        result = {"healthy": OK, "degraded": WARNING}.get(str(item["status"]), ERROR)
        out.append(_check(code, "data" if code.startswith("database") else "jobs", result, severity if result == ERROR else "medium",
                          latency_ms=item.get("latency_ms"), message=str(item.get("message") or "")[:250]))
    return out


def _database_account(db: Session) -> list[dict[str, Any]]:
    from app.services.infrastructure_service import database_info

    info = database_info(db)
    missing = list(info.get("missing_tables") or [])
    return [
        _check("database.tables", "data", ERROR if missing else OK, "high", count=len(missing), names=missing[:10]),
        _check("database.schema_rights", "data", WARNING if info.get("schema_rights") else OK, "medium", user=info.get("user")),
    ]


def _disk() -> dict[str, Any]:
    usage = shutil.disk_usage("/")
    percent = round(100.0 * usage.used / usage.total, 1) if usage.total else 0.0
    result = ERROR if percent >= DISK_ERROR_PERCENT else WARNING if percent >= DISK_WARNING_PERCENT else OK
    return _check("disk.space", "system", result, "critical" if result == ERROR else "medium", percent=percent,
                  free_gb=round(usage.free / 1024**3, 1), total_gb=round(usage.total / 1024**3, 1))


# ---- jobs and workers ---------------------------------------------------------------------------------------------

def _jobs(db: Session) -> list[dict[str, Any]]:
    from app.core.config import get_settings
    from app.services import job_board

    waiting = db.execute(text("""
        SELECT COUNT(*) AS n, MAX(TIMESTAMPDIFF(SECOND, created_at, UTC_TIMESTAMP())) AS oldest
        FROM provisioning_jobs WHERE status IN ('QUEUED', 'RETRYING')""")).mappings().first() or {}
    stuck_queue = int(db.execute(text("""
        SELECT COUNT(*) FROM provisioning_jobs WHERE status IN ('QUEUED', 'RETRYING')
          AND TIMESTAMPDIFF(SECOND, created_at, UTC_TIMESTAMP()) > :limit"""), {"limit": job_board.QUEUE_STUCK_SECONDS}).scalar() or 0)
    running = [dict(r) for r in db.execute(text("""
        SELECT id, job_type, status, TIMESTAMPDIFF(SECOND, started_at, UTC_TIMESTAMP()) AS run_seconds
        FROM provisioning_jobs WHERE status = 'RUNNING' AND started_at IS NOT NULL""")).mappings()]
    grace = get_settings().JOB_WATCHDOG_RUNNING_GRACE_SECONDS
    abandoned = [row for row in running if job_board.abandoned(row, grace)]
    return [
        _check("jobs.queue", "jobs", WARNING if stuck_queue else OK, "high", waiting=int(waiting.get("n") or 0),
               stuck=stuck_queue, oldest_seconds=int(waiting.get("oldest") or 0), limit_seconds=job_board.QUEUE_STUCK_SECONDS),
        _check("jobs.abandoned", "jobs", WARNING if abandoned else OK, "medium", running=len(running), count=len(abandoned),
               ids=[int(row["id"]) for row in abandoned[:10]]),
    ]


def _workers(db: Session) -> dict[str, Any]:
    from app.services.infrastructure_service import list_workers

    enabled = [w for w in list_workers(db) if w.get("is_enabled")]
    if not enabled:
        return _check("workers.available", "workers", ERROR, "critical", total=0, down=0, names=[])
    down = [w for w in enabled if w.get("status") != "healthy"]
    return _check("workers.available", "workers", ERROR if len(down) == len(enabled) else WARNING if down else OK,
                  "critical" if len(down) == len(enabled) else "high", total=len(enabled), down=len(down),
                  names=[str(w.get("name")) for w in down[:10]])


# ---- what the regular health check found --------------------------------------------------------------------------

def _components(db: Session) -> list[dict[str, Any]]:
    """Directories, their group OUs, file servers, SSO: the last result of the health check, and its age."""
    schedule = db.execute(text("SELECT interval_minutes, is_enabled, last_run_at FROM infra_schedules WHERE task = 'health_check'")).mappings().first()
    rows = [dict(r) for r in db.execute(text("SELECT component, label, status, checked_at FROM infra_component_status")).mappings()]
    out: list[dict[str, Any]] = []
    interval = int((schedule or {}).get("interval_minutes") or 5)
    last_run = (schedule or {}).get("last_run_at")
    stale = last_run is None or last_run < _now() - timedelta(minutes=max(15, interval * 3))
    out.append(_check("health.schedule", "system", WARNING if not (schedule or {}).get("is_enabled") or stale else OK, "medium",
                      enabled=bool((schedule or {}).get("is_enabled")), interval_minutes=interval,
                      last_run_minutes=int((_now() - last_run).total_seconds() // 60) if last_run else None))
    groups = (
        ("directories", "directory", lambda c: c.startswith("identity_source:"), "high"),
        ("group_ous", "permissions", lambda c: c.startswith("group_ou:"), "high"),
        ("file_servers", "storage", lambda c: c.startswith("storage_endpoint:"), "medium"),
        ("sso", "authentication", lambda c: c.startswith("sso:"), "medium"),
    )
    for code, area, match, severity in groups:
        mine = [r for r in rows if match(str(r["component"]))]
        if not mine:
            continue
        down = [r for r in mine if r["status"] == "down"]
        result = ERROR if mine and len(down) == len(mine) else WARNING if down else OK
        out.append(_check(f"components.{code}", area, result, severity, total=len(mine), down=len(down),
                          names=[str(r["label"]).split(" · ", 1)[-1] for r in down[:10]]))
    return out


def _fives(db: Session) -> list[dict[str, Any]]:
    from app.services import features, modules

    if not features.enabled(db, "fives"):
        return []
    return [_check("module.fives", "modules", OK if modules.fives_installed() else ERROR, "high")]


# ---- the report ---------------------------------------------------------------------------------------------------

def run(db: Session) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    checks += _guarded("config.internal_token", "configuration", "high", _internal_token)
    checks += _guarded("config.master_key", "configuration", "critical", _master_key)
    checks += _guarded("secrets.missing", "configuration", "high", lambda: _missing_secrets(db))
    checks += _guarded("database.application", "data", "critical", _live_connections)
    checks += _guarded("database.tables", "data", "high", lambda: _database_account(db))
    checks += _guarded("disk.space", "system", "medium", _disk)
    checks += _guarded("jobs.queue", "jobs", "high", lambda: _jobs(db))
    checks += _guarded("workers.available", "workers", "critical", lambda: _workers(db))
    checks += _guarded("health.schedule", "system", "medium", lambda: _components(db))
    checks += _guarded("module.fives", "modules", "high", lambda: _fives(db))
    summary = {result: sum(1 for c in checks if c["result"] == result) for result in (OK, WARNING, ERROR, UNKNOWN)}
    return {"checks": checks, "summary": {**summary, "total": len(checks)},
            "generated_at": _now().isoformat(timespec="seconds") + "Z"}
