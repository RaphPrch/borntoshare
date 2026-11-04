from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.services import extension_senders as senders
from app.services import extensions as ext
from app.services.platform_metrics import prometheus_text

ALERT = {
    "type": "alerts", "action": "acl_inherited_not_governed", "outcome": "open", "severity": "high",
    "summary": "Inherited ACL · Users reach 10 folders", "actor": "borntoshare", "target": "Paris - RH",
    "context": {"alert_key": "storage_root:1:acl_inherited_not_governed:utilisateurs"}, "at": "2026-11-04T12:00:00+00:00",
}


def test_loki_and_otlp_payloads() -> None:
    stream = senders.loki_payload(ALERT, "env=prod, team=iam")["streams"][0]
    assert stream["stream"] == {"app": "borntoshare", "type": "alerts", "severity": "high", "env": "prod", "team": "iam"}
    assert json.loads(stream["values"][0][1])["target"] == "Paris - RH"
    record = senders.otel_log_payload({"environment": "lab"}, ALERT)["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]
    assert record["severityText"] == "ERROR" and record["body"]["stringValue"].startswith("Inherited ACL")
    assert senders.otel_headers("Authorization=Bearer x; X-Scope-OrgID=b2s") == {"Authorization": "Bearer x", "X-Scope-OrgID": "b2s"}
    metrics = senders.otel_metrics_payload({}, [{"name": "b2s_alerts_open", "help": "h", "value": 3, "labels": {"severity": "high"}}])
    point = metrics["resourceMetrics"][0]["scopeMetrics"][0]["metrics"][0]["gauge"]["dataPoints"][0]
    assert point["asInt"] == "3" and point["attributes"][0]["key"] == "severity"


def test_prometheus_text() -> None:
    text = prometheus_text([
        {"name": "b2s_alerts_open", "help": "Open alerts", "value": 2, "labels": {"severity": "high"}},
        {"name": "b2s_alerts_open", "help": "Open alerts", "value": 0, "labels": {"severity": "critical"}},
        {"name": "b2s_storage_roots", "help": "Folders", "value": 158, "labels": {}},
    ])
    assert text.count("# TYPE b2s_alerts_open gauge") == 1 and 'b2s_alerts_open{severity="high"} 2' in text and "b2s_storage_roots 158" in text


class _Response:
    def __init__(self, status: int, body: dict) -> None:
        self.status_code, self._body, self.text = status, body, json.dumps(body)

    def json(self) -> dict:
        return self._body


def test_servicenow_incident_without_duplicate_then_resolved(monkeypatch) -> None:
    calls: list[tuple] = []
    open_incidents: list[dict] = []

    def get(url, params=None, **kwargs):
        calls.append(("GET", url, params))
        return _Response(200, {"result": list(open_incidents)})

    def post(url, json=None, **kwargs):
        calls.append(("POST", url, json))
        open_incidents.append({"sys_id": "abc", "number": "INC1"})
        return _Response(201, {"result": {"sys_id": "abc"}})

    def patch(url, json=None, **kwargs):
        calls.append(("PATCH", url, json))
        return _Response(200, {"result": {}})

    monkeypatch.setattr(senders.httpx, "get", get)
    monkeypatch.setattr(senders.httpx, "post", post)
    monkeypatch.setattr(senders.httpx, "patch", patch)
    config = {"instance_url": "https://corp.service-now.com", "auth": "basic", "username": "b2s", "assignment_group": "IAM"}
    senders.send_servicenow(config, "pw", ALERT)
    senders.send_servicenow(config, "pw", ALERT)  # the alert comes back: no second incident
    assert [c[0] for c in calls] == ["GET", "POST", "GET"]
    body = calls[1][2]
    assert body["correlation_id"].startswith("storage_root:1:") and (body["impact"], body["urgency"]) == ("2", "2") and body["assignment_group"] == "IAM"
    senders.send_servicenow(config, "pw", {**ALERT, "type": "alerts_resolved"})
    assert calls[-1][0] == "PATCH" and calls[-1][1].endswith("/incident/abc") and calls[-1][2]["state"] == "6"


def test_closed_alerts_follow_the_alert_routes() -> None:
    routes = {"audit": False, "alerts": True, "min_severity": "critical"}
    assert not ext.wanted(routes, {**ALERT, "type": "alerts_resolved"})
    assert ext.wanted({**routes, "min_severity": "high"}, {**ALERT, "type": "alerts_resolved"})
    assert senders.secrets_of('{"loki": "a", "grafana": ""}') == {"loki": "a"} and senders.secrets_of("x") == {}
