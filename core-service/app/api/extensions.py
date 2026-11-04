"""Advanced Settings › Extensions: configure where events go (syslog, Splunk) and the Centreon check."""
from __future__ import annotations

import hmac
import json
import secrets
import time
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api._helpers import ui_data
from app.core.db import get_db
from app.services import extensions as ext
from app.services.activity_log import log_activity
from app.services.authorization import actor_from_request, require_admin
from app.services.secret_store import resolve, store

router = APIRouter(prefix="/extensions", tags=["extensions"])


class ExtensionRoutes(BaseModel):
    audit: bool = True
    alerts: bool = True
    min_severity: Literal["info", "warning", "high", "critical"] = "high"


class ExtensionPayload(BaseModel):
    enabled: bool = False
    config: dict[str, Any] = Field(default_factory=dict)
    routes: ExtensionRoutes = Field(default_factory=ExtensionRoutes)
    # Left empty: the stored secret stays
    secret: str | None = Field(default=None, max_length=4096)


_ALLOWED = {
    "syslog": {"host", "port", "transport", "format", "facility", "app_name", "verify"},
    "splunk": {"url", "index", "sourcetype", "verify"},
    "centreon": set(),
    "grafana": {"loki_url", "loki_user", "labels", "grafana_url", "dashboard_uid"},
    "otel": {"endpoint", "service_namespace", "environment", "logs", "traces", "metrics", "sample_ratio"},
    "servicenow": {"instance_url", "auth", "username", "client_id", "assignment_group", "cmdb_ci", "category", "close_code"},
}
_URL_FIELDS = {"url", "loki_url", "grafana_url", "endpoint", "instance_url"}


def _clean(key: str, config: dict[str, Any]) -> dict[str, Any]:
    if key not in ext.CATALOG:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown extension")
    out = {name: value for name, value in config.items() if name in _ALLOWED[key] and value not in (None, "")}
    for name in _URL_FIELDS & set(out):
        if not str(out[name]).startswith(("https://", "http://")):
            raise HTTPException(status_code=422, detail={"code": "EXTENSION_CONFIG_INVALID", "message": "Les adresses commencent par https://"})
    if key == "otel":
        ratio = float(out.get("sample_ratio", 0.1))
        if not 0 <= ratio <= 1:
            raise HTTPException(status_code=422, detail={"code": "EXTENSION_CONFIG_INVALID", "message": "L'échantillonnage va de 0 à 1"})
        out["sample_ratio"] = ratio
    if key == "servicenow" and out.get("auth", "basic") not in {"basic", "oauth"}:
        raise HTTPException(status_code=422, detail={"code": "EXTENSION_CONFIG_INVALID", "message": "Authentification basic ou oauth"})
    if key == "syslog":
        if out.get("transport", "udp") not in {"udp", "tcp", "tls"} or out.get("format", "rfc5424") not in {"rfc5424", "cef", "json"}:
            raise HTTPException(status_code=422, detail={"code": "EXTENSION_CONFIG_INVALID", "message": "Transport or format not supported"})
        port = int(out.get("port") or 514)
        if not 1 <= port <= 65535:
            raise HTTPException(status_code=422, detail={"code": "EXTENSION_CONFIG_INVALID", "message": "The port goes from 1 to 65535"})
        out["port"] = port
    if key == "splunk" and out.get("url") and not str(out["url"]).startswith(("https://", "http://")):
        raise HTTPException(status_code=422, detail={"code": "EXTENSION_CONFIG_INVALID", "message": "The HEC URL starts with https://"})
    return out


def _row(db: Session, key: str) -> dict[str, Any] | None:
    return next((row for row in ext.load(db) if row["key"] == key), None)


@router.get("")
def list_extensions(request: Request, db: Session = Depends(get_db)):
    require_admin(actor_from_request(request))
    rows = {row["key"]: row for row in ext.load(db)}
    stats = ext.stats(db)
    items = []
    for key, meta in ext.CATALOG.items():
        row = rows.get(key) or {"enabled": False, "config": {}, "routes": dict(ext.DEFAULT_ROUTES), "secret_ref": None, "updated_at": None}
        items.append({
            "key": key,
            "events": meta["events"],
            "enabled": row["enabled"],
            "configured": key in rows,
            "config": row["config"],
            "routes": row["routes"],
            "has_secret": bool(row["secret_ref"]),
            "stats": stats.get(key),
        })
    return ui_data({"extensions": items, "health_path": "/monitoring/health"})


@router.put("/{key}")
def save_extension(key: str, payload: ExtensionPayload, request: Request, db: Session = Depends(get_db)):
    actor = actor_from_request(request)
    require_admin(actor)
    config = _clean(key, payload.config)
    current = _row(db, key)
    secret_ref = current["secret_ref"] if current else None
    token = None
    if key == "grafana":
        # Loki, annotations and the metrics token share one vault entry: a field left empty keeps its value
        from app.services.extension_senders import secrets_of

        keys = secrets_of(resolve(db, secret_ref)) if secret_ref else {}
        keys.update(secrets_of(payload.secret))
        if payload.enabled and not keys.get("metrics"):
            keys["metrics"] = token = secrets.token_urlsafe(32)
        if keys:
            secret_ref = store(db, "extension/grafana", json.dumps(keys))
    elif payload.secret:
        secret_ref = store(db, f"extension/{key}", payload.secret)
    if key == "centreon" and payload.enabled and not secret_ref:
        # The read-only token of the check, shown once
        token = secrets.token_urlsafe(32)
        secret_ref = store(db, "extension/centreon", token)
    if payload.enabled and ext.CATALOG[key]["secret"] and not secret_ref:
        raise HTTPException(status_code=422, detail={"code": "EXTENSION_SECRET_REQUIRED", "message": "The token is required"})
    db.execute(
        text(
            """
            INSERT INTO extensions (ext_key, enabled, config_json, routes_json, secret_ref, updated_by)
            VALUES (:key, :enabled, :config, :routes, :secret_ref, :by)
            ON DUPLICATE KEY UPDATE enabled = VALUES(enabled), config_json = VALUES(config_json),
              routes_json = VALUES(routes_json), secret_ref = VALUES(secret_ref), updated_by = VALUES(updated_by)
            """
        ),
        {"key": key, "enabled": int(payload.enabled), "config": json.dumps(config), "routes": json.dumps(payload.routes.model_dump()),
         "secret_ref": secret_ref, "by": actor.display_name},
    )
    db.commit()
    ext.forget_cache()
    log_activity(
        db, actor_type="user", actor_id=actor.identity_id, actor_display=actor.display_name,
        action="extension.updated", outcome="success", target_type="extension", target_display=key,
        context_json={"enabled": payload.enabled, "config": config, "routes": payload.routes.model_dump(), "secret_changed": bool(payload.secret)},
        correlation_id=(request.headers.get("x-request-id") or None),
    )
    return ui_data({"key": key, "enabled": payload.enabled, "token": token})


@router.post("/{key}/test")
def test_extension(key: str, payload: ExtensionPayload, request: Request, db: Session = Depends(get_db)):
    """Send a test event with the values of the form (not saved yet); the stored secret when none is typed."""
    require_admin(actor_from_request(request))
    config = _clean(key, payload.config)
    if not ext.CATALOG[key]["events"]:
        raise HTTPException(status_code=422, detail={"code": "EXTENSION_NOTHING_TO_SEND", "message": "This extension receives no event"})
    current = _row(db, key)
    secret = payload.secret or (resolve(db, current["secret_ref"]) if current and current["secret_ref"] else None)
    if key == "grafana" and payload.secret:
        from app.services.extension_senders import secrets_of

        stored = secrets_of(resolve(db, current["secret_ref"])) if current and current["secret_ref"] else {}
        secret = json.dumps({**stored, **secrets_of(payload.secret)})
    started = time.monotonic()
    try:
        if key == "servicenow":
            from app.services.extension_senders import servicenow_check

            servicenow_check(config, secret)
        else:
            # Grafana: an alert, so that the annotations are tried too
            event = {**ext.test_event(), "type": "alerts"} if key == "grafana" else ext.test_event()
            ext.deliver(key, config, secret, event)
    except Exception as exc:
        return ui_data({"ok": False, "error": str(exc)[:300]})
    return ui_data({"ok": True, "latency_ms": int((time.monotonic() - started) * 1000)})


@router.post("/centreon/token")
def renew_centreon_token(request: Request, db: Session = Depends(get_db)):
    actor = actor_from_request(request)
    require_admin(actor)
    token = secrets.token_urlsafe(32)
    ref = store(db, "extension/centreon", token)
    db.execute(
        text(
            """
            INSERT INTO extensions (ext_key, enabled, secret_ref, updated_by) VALUES ('centreon', 1, :ref, :by)
            ON DUPLICATE KEY UPDATE secret_ref = VALUES(secret_ref), updated_by = VALUES(updated_by)
            """
        ),
        {"ref": ref, "by": actor.display_name},
    )
    db.commit()
    log_activity(
        db, actor_type="user", actor_id=actor.identity_id, actor_display=actor.display_name,
        action="extension.token_renewed", outcome="success", target_type="extension", target_display="centreon",
        correlation_id=(request.headers.get("x-request-id") or None),
    )
    return ui_data({"token": token})


@router.get("/deliveries")
def list_deliveries(request: Request, limit: int = 50, db: Session = Depends(get_db)):
    require_admin(actor_from_request(request))
    try:
        rows = db.execute(
            text(
                """
                SELECT id, ext_key, event_type, summary, status, detail, attempts, latency_ms, created_at
                FROM extension_deliveries ORDER BY id DESC LIMIT :limit
                """
            ),
            {"limit": max(1, min(int(limit), 200))},
        ).mappings().all()
    except Exception:
        db.rollback()
        rows = []
    return ui_data([{**dict(row), "created_at": row["created_at"].isoformat() + "Z"} for row in rows])


@router.get("/centreon/check")
def centreon_check(request: Request, db: Session = Depends(get_db)):
    """Platform state for Centreon (called by the frontend route /monitoring/health with the check token):
    OK when every monitored component answers, CRITICAL with the components down otherwise."""
    from app.api.observability import _health

    provided = request.headers.get("x-monitoring-token", "")
    row = _row(db, "centreon")
    expected = resolve(db, row["secret_ref"]) if row and row["enabled"] and row["secret_ref"] else ""
    if not expected or not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Monitoring token refused")
    health = _health(db)
    down = [item["label"] for item in health["down"]]
    degraded = [item["label"] for item in health["degraded"]]
    if down:
        state, line = "CRITICAL", f"CRITICAL - {len(down)} component(s) down: {', '.join(down[:10])}"
    elif degraded:
        state, line = "WARNING", f"WARNING - {len(degraded)} component(s) degraded: {', '.join(degraded[:10])}"
    else:
        state, line = "OK", "OK - every monitored component answers"
    return ui_data({"state": state, "text": line})


@router.get("/grafana/metrics")
def grafana_metrics(request: Request, db: Session = Depends(get_db)):
    """Figures of the platform for Prometheus / Grafana (called by the frontend route /monitoring/metrics)."""
    from app.services.extension_senders import secrets_of
    from app.services.platform_metrics import prometheus_text, snapshot

    provided = request.headers.get("x-monitoring-token", "")
    row = _row(db, "grafana")
    expected = secrets_of(resolve(db, row["secret_ref"])).get("metrics", "") if row and row["enabled"] and row["secret_ref"] else ""
    if not expected or not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Metrics token refused")
    return ui_data({"text": prometheus_text(snapshot(db))})

