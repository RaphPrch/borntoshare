from __future__ import annotations

import json
import socket
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.services import extensions as ext

EVENT = {
    "type": "audit", "action": "access_request.created", "outcome": "success", "severity": "info",
    "summary": "access_request.created REQ-927", "actor": "paul.martin", "target": "Paris - Finance",
    "context": {}, "at": "2026-11-04T10:41:55+00:00",
}


def test_syslog_formats() -> None:
    line = ext.syslog_line(EVENT, {"format": "rfc5424", "facility": "local4"})
    assert line.startswith("<166>1 2026-11-04T10:41:55+00:00 ")  # local4 (20) * 8 + info (6)
    assert ' borntoshare - access_request.created [b2s@32473 actor="paul.martin" target="Paris - Finance" outcome="success"] ' in line
    cef = ext.syslog_line({**EVENT, "summary": "a|b"}, {"format": "cef"})
    assert cef.startswith("CEF:0|BornToShare|BornToShare|1.0|access_request.created|a\\|b|3|") and "suser=paul.martin" in cef
    assert json.loads(ext.syslog_line(EVENT, {"format": "json"}))["actor"] == "paul.martin"


def test_alerts_below_the_minimal_severity_stay_home() -> None:
    routes = {"audit": False, "alerts": True, "min_severity": "high"}
    assert not ext.wanted(routes, EVENT)
    assert ext.wanted(routes, {**EVENT, "type": "alerts", "severity": "critical"})
    assert not ext.wanted(routes, {**EVENT, "type": "alerts", "severity": "warning"})


def test_a_udp_line_reaches_the_collector() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as server:
        server.bind(("127.0.0.1", 0))
        server.settimeout(2)
        ext.send_syslog({"host": "127.0.0.1", "port": server.getsockname()[1], "transport": "udp"}, "hello")
        assert server.recvfrom(1024)[0] == b"hello"


def test_splunk_refusal_is_an_error(monkeypatch) -> None:
    class _Response:
        status_code = 403
        text = "Invalid token"

    seen = {}
    monkeypatch.setattr(ext.httpx, "post", lambda url, **kwargs: seen.update(kwargs) or _Response())
    with pytest.raises(RuntimeError, match="HTTP 403"):
        ext.send_splunk({"url": "https://splunk:8088/services/collector", "index": "b2s"}, "tok", EVENT)
    assert seen["headers"]["Authorization"] == "Splunk tok" and seen["json"]["index"] == "b2s"


def test_config_is_checked(monkeypatch) -> None:
    from fastapi import HTTPException

    from app.api import extensions as api

    assert api._clean("syslog", {"host": "siem", "port": "6514", "transport": "tls", "other": 1}) == {"host": "siem", "port": 6514, "transport": "tls"}
    with pytest.raises(HTTPException):
        api._clean("syslog", {"transport": "carrier-pigeon"})
    with pytest.raises(HTTPException):
        api._clean("splunk", {"url": "ftp://splunk"})
