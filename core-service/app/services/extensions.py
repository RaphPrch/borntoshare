"""Extensions (Advanced Settings › Extensions): BornToShare events sent to the tools of the company.

- syslog: audit and alerts to a syslog collector (RFC 5424, CEF or JSON; UDP, TCP or TLS)
- splunk: the same to a Splunk HTTP Event Collector
- centreon: Centreon polls the platform state (GET /monitoring/health with a read-only token), nothing is pushed

Events leave from core-service in the background: a send never slows down nor fails a request. Each send is
tried 3 times and written to extension_deliveries (Advanced Settings › Extensions › Deliveries).
"""
from __future__ import annotations

import json
import logging
import socket
import ssl
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

CERTS_DIR = Path("/etc/b2s/certs")
EVENT_TYPES = ("audit", "alerts")
SEVERITIES = ("info", "warning", "high", "critical")
CATALOG: dict[str, dict[str, Any]] = {
    "syslog": {"events": ["audit", "alerts"], "secret": False},
    "splunk": {"events": ["audit", "alerts"], "secret": True},
    "centreon": {"events": [], "secret": True},
    # Loki (events), annotations (alerts), /monitoring/metrics (scraped with its token)
    "grafana": {"events": ["audit", "alerts"], "secret": True},
    # OTLP/HTTP: events as logs, core-service requests as traces, platform figures as metrics
    "otel": {"events": ["audit", "alerts"], "secret": False},
    # One incident per new alert, resolved when the alert closes
    "servicenow": {"events": ["alerts", "alerts_resolved"], "secret": True},
}
DEFAULT_ROUTES = {"audit": True, "alerts": True, "min_severity": "high"}
RETRY_DELAYS = (0, 2, 10)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="b2s-extensions")
_cache: dict[str, Any] = {"at": 0.0, "rows": []}


# ---- events ---------------------------------------------------------------------------------

def event_from_activity(payload: dict[str, Any]) -> dict[str, Any]:
    action = str(payload.get("action") or "")
    target = payload.get("target_display") or payload.get("target_id") or ""
    return {
        "type": "audit",
        "action": action,
        "outcome": payload.get("outcome"),
        "severity": "warning" if str(payload.get("outcome") or "") in {"failure", "denied"} else "info",
        "summary": f"{action} {target}".strip(),
        "actor": payload.get("actor_display") or payload.get("actor_id"),
        "target": target,
        "context": payload.get("context_json") or {},
        "at": datetime.now(timezone.utc).isoformat(),
    }


def event_from_alert(alert: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "alerts",
        "action": str(alert.get("alert_type") or "alert"),
        "outcome": "open",
        "severity": str(alert.get("severity") or "warning"),
        "summary": f"{alert.get('title') or ''} · {alert.get('message') or ''}".strip(" ·"),
        "actor": "borntoshare",
        "target": (alert.get("metadata_json") or {}).get("storage_root_name") if isinstance(alert.get("metadata_json"), dict) else None,
        "context": {"alert_key": alert.get("alert_key")},
        "at": datetime.now(timezone.utc).isoformat(),
    }


def event_from_resolved_alert(alert: dict[str, Any]) -> dict[str, Any]:
    return {**event_from_alert(alert), "type": "alerts_resolved", "outcome": "resolved"}


def wanted(routes: dict[str, Any], event: dict[str, Any]) -> bool:
    # A closed alert follows its alert: sent where the alert was sent
    kind = "alerts" if event["type"] == "alerts_resolved" else event["type"]
    if not routes.get(kind):
        return False
    if kind == "alerts":
        floor = SEVERITIES.index(routes.get("min_severity", "high")) if routes.get("min_severity") in SEVERITIES else 2
        level = SEVERITIES.index(event["severity"]) if event["severity"] in SEVERITIES else 1
        return level >= floor
    return True


# ---- formats ----------------------------------------------------------------------------------

_FACILITIES = {"local0": 16, "local1": 17, "local2": 18, "local3": 19, "local4": 20, "local5": 21, "local6": 22, "local7": 23, "auth": 4}
_SYSLOG_SEVERITY = {"critical": 2, "high": 3, "warning": 4, "info": 6}
_CEF_SEVERITY = {"critical": 10, "high": 8, "warning": 5, "info": 3}


def _cef_escape(value: Any, header: bool = False) -> str:
    text_value = str(value if value is not None else "").replace("\\", "\\\\")
    return text_value.replace("|", "\\|") if header else text_value.replace("=", "\\=").replace("\n", " ")


def syslog_line(event: dict[str, Any], config: dict[str, Any]) -> str:
    fmt = str(config.get("format") or "rfc5424")
    app = str(config.get("app_name") or "borntoshare")[:48]
    if fmt == "json":
        return json.dumps({"app": app, **event}, ensure_ascii=False, default=str)
    if fmt == "cef":
        extension = " ".join(
            f"{key}={_cef_escape(value)}"
            for key, value in (("act", event["action"]), ("outcome", event["outcome"]), ("suser", event["actor"]), ("fname", event["target"]), ("msg", event["summary"]))
            if value
        )
        return (
            f"CEF:0|BornToShare|BornToShare|1.0|{_cef_escape(event['action'], True)}|"
            f"{_cef_escape(event['summary'], True)}|{_CEF_SEVERITY.get(event['severity'], 3)}|{extension}"
        )
    pri = _FACILITIES.get(str(config.get("facility") or "local4"), 20) * 8 + _SYSLOG_SEVERITY.get(event["severity"], 6)
    host = socket.gethostname()[:255] or "-"
    data = " ".join(
        f'{key}="{str(value).replace(chr(92), chr(92) * 2).replace(chr(34), chr(92) + chr(34)).replace("]", chr(92) + "]")}"'
        for key, value in (("actor", event["actor"]), ("target", event["target"]), ("outcome", event["outcome"]))
        if value
    )
    structured = f"[b2s@32473 {data}]" if data else "-"
    msgid = str(event["action"] or "-")[:32].replace(" ", "_")
    return f"<{pri}>1 {event['at']} {host} {app} - {msgid} {structured} {event['summary']}"


# ---- senders ----------------------------------------------------------------------------------

def _verify(config: dict[str, Any], ca_file: str) -> ssl.SSLContext | bool:
    mode = str(config.get("verify") or "public")
    if mode == "none":
        return False
    path = CERTS_DIR / ca_file
    if mode == "file" and path.is_file():
        return ssl.create_default_context(cafile=str(path))
    return True


def send_syslog(config: dict[str, Any], line: str) -> None:
    host = str(config.get("host") or "").strip()
    port = int(config.get("port") or 514)
    transport = str(config.get("transport") or "udp")
    if not host:
        raise ValueError("No syslog server")
    data = line.encode("utf-8")
    if transport == "udp":
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(5)
            sock.sendto(data, (host, port))
        return
    with socket.create_connection((host, port), timeout=5) as raw:
        if transport == "tls":
            verify = _verify(config, "syslog-ca.pem")
            context = verify if isinstance(verify, ssl.SSLContext) else ssl.create_default_context()
            if verify is False:
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
            with context.wrap_socket(raw, server_hostname=host) as sock:
                sock.sendall(data + b"\n")
        else:
            raw.sendall(data + b"\n")


def send_splunk(config: dict[str, Any], secret: str, event: dict[str, Any]) -> None:
    url = str(config.get("url") or "").strip()
    if not url or not secret:
        raise ValueError("No HEC URL or token")
    body: dict[str, Any] = {"time": time.time(), "host": "borntoshare", "source": "borntoshare", "event": event}
    if config.get("index"):
        body["index"] = config["index"]
    body["sourcetype"] = config.get("sourcetype") or f"borntoshare:{event['type']}"
    response = httpx.post(url, json=body, headers={"Authorization": f"Splunk {secret}"}, timeout=8, verify=_verify(config, "splunk-ca.pem"))
    if response.status_code >= 300:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:160]}")


def deliver(key: str, config: dict[str, Any], secret: str | None, event: dict[str, Any]) -> None:
    from app.services import extension_senders as senders

    if event["type"] not in CATALOG.get(key, {}).get("events", []) and event["action"] != "borntoshare.test":
        return
    if key == "syslog":
        send_syslog(config, syslog_line(event, config))
    elif key == "splunk":
        send_splunk(config, secret or "", event)
    elif key == "grafana":
        senders.send_grafana(config, secret, event)
    elif key == "otel":
        senders.send_otel(config, secret, event)
    elif key == "servicenow":
        senders.send_servicenow(config, secret, event)
    else:
        raise ValueError(f"{key} receives no event")


# ---- configuration --------------------------------------------------------------------------------

def _json(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value) if value else default
    except (TypeError, ValueError):
        return default


def load(db: Session) -> list[dict[str, Any]]:
    try:
        rows = db.execute(text("SELECT ext_key, enabled, config_json, routes_json, secret_ref, updated_at FROM extensions")).mappings().all()
    except Exception:  # table not created yet (pack 147)
        db.rollback()
        return []
    return [
        {
            "key": row["ext_key"],
            "enabled": bool(row["enabled"]),
            "config": _json(row["config_json"], {}),
            "routes": {**DEFAULT_ROUTES, **_json(row["routes_json"], {})},
            "secret_ref": row["secret_ref"],
            "updated_at": row["updated_at"],
        }
        for row in rows
        if row["ext_key"] in CATALOG
    ]


def _active(db_factory) -> list[dict[str, Any]]:
    """Enabled extensions, re-read every 30 s: an event costs no database read."""
    if time.monotonic() - _cache["at"] > 30:
        db = db_factory()
        try:
            _cache["rows"] = [row for row in load(db) if row["enabled"] and CATALOG[row["key"]]["events"]]
        finally:
            db.close()
        _cache["at"] = time.monotonic()
    return _cache["rows"]


def forget_cache() -> None:
    _cache["at"] = 0.0


# ---- dispatch -------------------------------------------------------------------------------------

def record(db: Session, key: str, event: dict[str, Any], status: str, detail: str | None, attempts: int, latency_ms: int | None) -> None:
    db.execute(
        text(
            """
            INSERT INTO extension_deliveries (ext_key, event_type, summary, status, detail, attempts, latency_ms)
            VALUES (:key, :type, :summary, :status, :detail, :attempts, :latency)
            """
        ),
        {"key": key, "type": event["type"], "summary": str(event["summary"])[:255], "status": status,
         "detail": (detail or "")[:500] or None, "attempts": attempts, "latency": latency_ms},
    )
    db.execute(text("DELETE FROM extension_deliveries WHERE created_at < NOW() - INTERVAL 7 DAY"))
    db.commit()


def _send_with_retries(key: str, event: dict[str, Any]) -> None:
    from app.core.db import SessionLocal
    from app.services.secret_store import resolve

    db = SessionLocal()
    try:
        row = next((r for r in load(db) if r["key"] == key), None)
        if row is None or not row["enabled"]:
            return
        secret = resolve(db, row["secret_ref"]) if row["secret_ref"] else None
        error = None
        for attempt, delay in enumerate(RETRY_DELAYS, start=1):
            time.sleep(delay)
            started = time.monotonic()
            try:
                deliver(key, row["config"], secret, event)
                record(db, key, event, "delivered", None, attempt, int((time.monotonic() - started) * 1000))
                return
            except Exception as exc:  # network, refusal: tried again, then recorded
                error = str(exc)[:300]
        record(db, key, event, "failed", error, len(RETRY_DELAYS), None)
    except Exception:
        logger.warning("EXTENSION_DELIVERY_FAILED", exc_info=True)
    finally:
        db.close()


def dispatch(event: dict[str, Any]) -> None:
    """Hand an event to the enabled extensions that want it; never raises, never blocks."""
    try:
        from app.core.db import SessionLocal

        for row in _active(SessionLocal):
            if event["type"] in CATALOG[row["key"]]["events"] and wanted(row["routes"], event):
                _executor.submit(_send_with_retries, row["key"], event)
    except Exception:
        logger.warning("EXTENSION_DISPATCH_FAILED", exc_info=True)


def test_event() -> dict[str, Any]:
    return {
        "type": "audit", "action": "borntoshare.test", "outcome": "success", "severity": "info",
        "summary": "BornToShare test event", "actor": "borntoshare", "target": None, "context": {},
        "at": datetime.now(timezone.utc).isoformat(),
    }


def stats(db: Session) -> dict[str, dict[str, Any]]:
    """Per extension: sends of the last 24 h, the last result, and 12 two-hour buckets for the sparkline."""
    out: dict[str, dict[str, Any]] = {}
    try:
        rows = db.execute(
            text(
                """
                SELECT ext_key, status, created_at, detail,
                       FLOOR(TIMESTAMPDIFF(MINUTE, created_at, NOW()) / 120) AS bucket
                FROM extension_deliveries
                WHERE created_at >= NOW() - INTERVAL 24 HOUR
                ORDER BY created_at DESC
                """
            )
        ).mappings().all()
    except Exception:
        db.rollback()
        return out
    for row in rows:
        entry = out.setdefault(row["ext_key"], {"sent": 0, "failed": 0, "last_status": row["status"], "last_at": row["created_at"].isoformat() + "Z", "last_detail": row["detail"], "buckets": [0] * 12, "failed_buckets": [0] * 12})
        bucket = 11 - min(11, int(row["bucket"] or 0))
        if row["status"] == "delivered":
            entry["sent"] += 1
            entry["buckets"][bucket] += 1
        else:
            entry["failed"] += 1
            entry["failed_buckets"][bucket] += 1
    return out
