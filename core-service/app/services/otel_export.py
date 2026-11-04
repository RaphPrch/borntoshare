"""OpenTelemetry of core-service (Advanced Settings › Extensions › OpenTelemetry), without SDK.

- traces: one span per HTTP request (sampled, W3C traceparent kept), sent every 5 seconds
- metrics: the figures of the platform, every minute
Everything runs in one background thread; nothing happens while the extension is disabled.
"""
from __future__ import annotations

import logging
import random
import re
import secrets
import threading
import time
from collections import deque
from typing import Any

logger = logging.getLogger(__name__)
_spans: deque[dict[str, Any]] = deque(maxlen=2000)
_state: dict[str, Any] = {"at": 0.0, "config": None, "headers": None, "thread": None, "metrics_at": 0.0}
_TRACEPARENT = re.compile(r"^00-([0-9a-f]{32})-([0-9a-f]{16})-[0-9a-f]{2}$")


def _settings() -> tuple[dict[str, Any] | None, str | None]:
    """Enabled OpenTelemetry config and its headers secret, re-read every 30 s."""
    if time.monotonic() - _state["at"] > 30:
        _state["at"] = time.monotonic()
        config, headers = None, None
        try:
            from app.core.db import SessionLocal
            from app.services.extensions import load
            from app.services.secret_store import resolve

            db = SessionLocal()
            try:
                row = next((r for r in load(db) if r["key"] == "otel" and r["enabled"]), None)
                if row:
                    config = row["config"]
                    headers = resolve(db, row["secret_ref"]) if row["secret_ref"] else None
            finally:
                db.close()
        except Exception:
            logger.debug("OTEL_SETTINGS_UNREADABLE", exc_info=True)
        _state["config"], _state["headers"] = config, headers
    return _state["config"], _state["headers"]


def record_span(method: str, route: str, status: int, start_ns: int, end_ns: int, traceparent: str | None) -> None:
    config, _ = _settings()
    if not config or not config.get("traces", True) or random.random() >= float(config.get("sample_ratio", 0.1)):
        return
    parent = _TRACEPARENT.match(str(traceparent or "").strip())
    span = {
        "traceId": parent.group(1) if parent else secrets.token_hex(16),
        "spanId": secrets.token_hex(8),
        "name": f"{method} {route}",
        "kind": 2,  # server
        "startTimeUnixNano": str(start_ns),
        "endTimeUnixNano": str(end_ns),
        "attributes": [
            {"key": "http.request.method", "value": {"stringValue": method}},
            {"key": "http.route", "value": {"stringValue": route}},
            {"key": "http.response.status_code", "value": {"intValue": str(status)}},
        ],
        "status": {"code": 2 if status >= 500 else 1},
    }
    if parent:
        span["parentSpanId"] = parent.group(2)
    _spans.append(span)
    _start()


def _loop() -> None:
    from app.services.extension_senders import otel_metrics_payload, otel_post, otel_traces_payload

    while True:
        time.sleep(5)
        try:
            config, headers = _settings()
            if not config:
                _spans.clear()
                continue
            batch = [_spans.popleft() for _ in range(min(len(_spans), 500))]
            if batch:
                otel_post(config, headers, "traces", otel_traces_payload(config, batch))
            if config.get("metrics", True) and time.monotonic() - _state["metrics_at"] > 60:
                _state["metrics_at"] = time.monotonic()
                from app.core.db import SessionLocal
                from app.services.platform_metrics import snapshot

                db = SessionLocal()
                try:
                    figures = snapshot(db)
                finally:
                    db.close()
                otel_post(config, headers, "metrics", otel_metrics_payload(config, figures))
        except Exception as exc:
            logger.warning("OTEL_EXPORT_FAILED", extra={"error": str(exc)[:200]})


def _start() -> None:
    if _state["thread"] is None or not _state["thread"].is_alive():
        _state["thread"] = threading.Thread(target=_loop, name="b2s-otel", daemon=True)
        _state["thread"].start()


def start_if_enabled() -> None:
    """At startup: metrics are sent even when no request comes."""
    config, _ = _settings()
    if config:
        _start()
