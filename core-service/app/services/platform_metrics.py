"""Figures of the platform for Grafana / Prometheus (GET /monitoring/metrics) and OpenTelemetry (OTLP metrics)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

_SEVERITIES = ("info", "warning", "high", "critical")


def snapshot(db: Session) -> list[dict[str, Any]]:
    """[{name, help, value, labels}] read from the database; a figure that cannot be read is left out."""
    out: list[dict[str, Any]] = []

    def one(sql: str) -> int | None:
        try:
            return int(db.execute(text(sql)).scalar() or 0)
        except Exception:
            db.rollback()
            return None

    try:
        rows = db.execute(text("SELECT LOWER(severity) AS s, COUNT(*) AS n FROM governance_alerts WHERE status = 'open' GROUP BY LOWER(severity)")).mappings().all()
        counts = {row["s"]: int(row["n"]) for row in rows}
        for severity in _SEVERITIES:
            out.append({"name": "b2s_alerts_open", "help": "Open governance alerts", "value": counts.get(severity, 0), "labels": {"severity": severity}})
    except Exception:
        db.rollback()
    figures = (
        ("b2s_access_requests_pending", "Access requests waiting for a decision", "SELECT COUNT(*) FROM access_requests WHERE status = 'pending'"),
        ("b2s_storage_roots", "Governed folders", "SELECT COUNT(*) FROM storage_roots WHERE deleted_at IS NULL"),
        ("b2s_extension_deliveries_failed_24h", "Extension sends that failed in the last 24 hours",
         "SELECT COUNT(*) FROM extension_deliveries WHERE status = 'failed' AND created_at >= NOW() - INTERVAL 24 HOUR"),
    )
    for name, help_text, sql in figures:
        value = one(sql)
        if value is not None:
            out.append({"name": name, "help": help_text, "value": value, "labels": {}})
    try:
        from app.api.observability import _health

        health = _health(db)
        out.append({"name": "b2s_components_down", "help": "Monitored components down", "value": len(health["down"]), "labels": {}})
        out.append({"name": "b2s_components_degraded", "help": "Monitored components degraded", "value": len(health["degraded"]), "labels": {}})
    except Exception:
        db.rollback()
    return out


def prometheus_text(figures: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    seen: set[str] = set()
    for figure in figures:
        if figure["name"] not in seen:
            seen.add(figure["name"])
            lines.append(f"# HELP {figure['name']} {figure['help']}")
            lines.append(f"# TYPE {figure['name']} gauge")
        labels = ",".join(f'{key}="{value}"' for key, value in figure["labels"].items())
        lines.append(f"{figure['name']}{{{labels}}} {figure['value']}" if labels else f"{figure['name']} {figure['value']}")
    return "\n".join(lines) + "\n"
