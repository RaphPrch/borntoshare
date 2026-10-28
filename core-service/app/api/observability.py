"""Observability › Overview (platform administrators): one answer to « is everything all right? ».

Aggregates, for the chosen period: platform health (latest checks), open alerts grouped by type,
failed or stuck jobs, refused sign-ins, and the latest business events.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api._helpers import ui_data
from app.core.db import get_db
from app.services.authorization import actor_from_request, require_observability

router = APIRouter(prefix="/observability", tags=["observability"])

PERIOD_HOURS = {"24h": 24, "7d": 24 * 7, "30d": 24 * 30}
SEVERITY_RANK = {"critical": 4, "high": 3, "warning": 2, "info": 1}
STUCK_MINUTES = 5


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() + ("Z" if getattr(value, "tzinfo", None) is None else "")


def _health(db: Session) -> dict[str, Any]:
    from app.services.infrastructure_service import overview as infra_overview

    data = infra_overview(db)
    families: dict[str, dict[str, Any]] = {}
    for component in data["components"]:
        entry = families.setdefault(component["category"], {"key": component["category"], "total": 0, "up": 0, "down": 0, "degraded": 0, "unknown": 0})
        entry["total"] += 1
        status = component["status"]
        if status in {"healthy", "degraded"}:
            entry["up"] += 1
        if status in {"down", "degraded", "unknown"}:
            entry[status] += 1
    for entry in families.values():
        entry["status"] = (
            "down" if entry["down"] else "degraded" if entry["degraded"] else "unknown" if entry["unknown"] == entry["total"] else "healthy"
        )
    uptimes = [c["uptime_24h"] for c in data["components"] if c["uptime_24h"] is not None]
    schedule = db.execute(text("SELECT next_run_at FROM infra_schedules WHERE task = 'health_check'")).scalar()

    def brief(c: dict[str, Any]) -> dict[str, Any]:
        return {"component": c["component"], "label": c["label"], "message": c["message"]}

    return {
        "summary": data["summary"],
        "families": list(families.values()),
        "down": [brief(c) for c in data["components"] if c["status"] == "down"],
        "degraded": [brief(c) for c in data["components"] if c["status"] == "degraded"],
        "last_check_at": max((c["checked_at"] for c in data["components"] if c["checked_at"]), default=None),
        "next_check_at": _iso(schedule),
        "uptime_24h": round(sum(uptimes) / len(uptimes), 1) if uptimes else None,
    }


def _alerts(db: Session, hours: int) -> dict[str, Any]:
    rows = [
        dict(r)
        for r in db.execute(
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
            )
        ).mappings()
    ]
    critical = [r for r in rows if r["status"] == "open" and r["severity"] in {"critical", "high"}]
    new_critical = db.execute(
        text(
            """
            SELECT COUNT(*) FROM governance_alerts
            WHERE severity IN ('critical', 'high') AND first_seen_at >= UTC_TIMESTAMP() - INTERVAL :hours HOUR
            """
        ),
        {"hours": hours},
    ).scalar()

    # « Endpoint unreachable × 47 » rather than 47 lines: one group per type, worst severity first
    groups: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row["status"] != "open":
            continue
        key = str(row["alert_type"] or "other").split(":")[0]
        group = groups.setdefault(key, {"alert_type": key, "count": 0, "severity": "info", "titles": Counter(), "scopes": set(), "last_seen_at": None, "example": None})
        group["count"] += 1
        group["titles"][row["title"]] += 1
        if row["scope_name"]:
            group["scopes"].add(row["scope_name"])
        if SEVERITY_RANK.get(row["severity"], 0) > SEVERITY_RANK.get(group["severity"], 0):
            group["severity"] = row["severity"]
        if group["last_seen_at"] is None or (row["last_seen_at"] and row["last_seen_at"] > group["last_seen_at"]):
            group["last_seen_at"] = row["last_seen_at"]
            group["example"] = row["message"]
    top = sorted(groups.values(), key=lambda g: (-SEVERITY_RANK.get(g["severity"], 0), -g["count"]))[:5]
    return {
        "critical_open": len(critical),
        "critical_new": int(new_critical or 0),
        "warnings_open": sum(1 for r in rows if r["status"] == "open" and r["severity"] == "warning"),
        "acknowledged": sum(1 for r in rows if r["status"] == "acknowledged"),
        "groups": [
            {
                "alert_type": g["alert_type"],
                "title": g["titles"].most_common(1)[0][0],
                "severity": g["severity"],
                "count": g["count"],
                "scopes": sorted(g["scopes"])[:3],
                "scope_count": len(g["scopes"]),
                "example": g["example"],
                "last_seen_at": _iso(g["last_seen_at"]),
            }
            for g in top
        ],
    }


def _jobs(db: Session, hours: int) -> dict[str, Any]:
    counts = db.execute(
        text(
            """
            SELECT
              COUNT(*) AS total,
              SUM(UPPER(status) = 'FAILED') AS failed
            FROM provisioning_jobs
            WHERE created_at >= NOW() - INTERVAL :hours HOUR
            """
        ),
        {"hours": hours},
    ).mappings().first() or {}
    stuck = db.execute(
        text(
            """
            SELECT COUNT(*) FROM provisioning_jobs
            WHERE UPPER(status) IN ('QUEUED', 'RETRYING') AND updated_at < NOW() - INTERVAL :minutes MINUTE
            """
        ),
        {"minutes": STUCK_MINUTES},
    ).scalar()
    items = [
        {**dict(r), "updated_at": _iso(r["updated_at"])}
        for r in db.execute(
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
            {"hours": hours},
        ).mappings()
    ]
    return {"total": int(counts.get("total") or 0), "failed": int(counts.get("failed") or 0), "stuck": int(stuck or 0), "items": items}


def _sign_ins(hours: int) -> dict[str, Any]:
    from app.core.logging_db import LoggingSessionLocal

    with LoggingSessionLocal() as logging_db:
        rows = logging_db.execute(
            text(
                """
                SELECT result,
                       JSON_UNQUOTE(JSON_EXTRACT(metadata_json, '$.reason')) AS reason,
                       COUNT(*) AS n
                FROM audit_event
                WHERE action = 'auth.login' AND event_time >= UTC_TIMESTAMP() - INTERVAL :hours HOUR
                GROUP BY result, reason
                """
            ),
            {"hours": hours},
        ).mappings().all()
    refused = Counter()
    total = 0
    for row in rows:
        total += int(row["n"])
        if str(row["result"]).lower() in {"failure", "failed"}:
            refused[str(row["reason"] or "UNKNOWN")] += int(row["n"])
    return {"total": total, "refused": sum(refused.values()), "reasons": dict(refused)}


@router.get("/overview")
def get_overview(request: Request, period: Literal["24h", "7d", "30d"] = "24h", db: Session = Depends(get_db)):
    from app.services.activity_bridge import list_activity_latest

    require_observability(actor_from_request(request))
    hours = PERIOD_HOURS[period]
    try:
        events = list_activity_latest(limit=8, business_only=True)
    except Exception:
        events = []
    try:
        sign_ins = _sign_ins(hours)
    except Exception:
        sign_ins = {"total": 0, "refused": 0, "reasons": {}, "unavailable": True}
    return ui_data(
        {
            "period": period,
            "health": _health(db),
            "alerts": _alerts(db, hours),
            "jobs": _jobs(db, hours),
            "sign_ins": sign_ins,
            "events": events if isinstance(events, list) else [],
        }
    )


@router.get("/badge")
def get_badge(request: Request, db: Session = Depends(get_db)):
    """Open critical or high alerts, for the top bar pill (cheap: one count)."""
    require_observability(actor_from_request(request))
    count = db.execute(
        text("SELECT COUNT(*) FROM governance_alerts WHERE status = 'open' AND severity IN ('critical', 'high')")
    ).scalar()
    return ui_data({"critical_open": int(count or 0)})
