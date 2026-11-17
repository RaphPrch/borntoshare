"""Senders of the extensions Grafana (Loki, annotations), OpenTelemetry (OTLP/HTTP JSON), ServiceNow (Table API),
OpenSearch (document API), RabbitMQ (HTTP API of the management plugin) and MinIO / S3 (PUT, AWS Signature V4).

Pure HTTP with httpx: no SDK to install, the payloads are built here and tested.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid
from datetime import datetime, timezone
from urllib.parse import quote, urlparse
import socket
import time
from typing import Any

import httpx

TIMEOUT = 10
_IMPACT = {"critical": ("1", "1"), "high": ("2", "2"), "warning": ("3", "3"), "info": ("3", "3")}
_OTEL_SEVERITY = {"info": (9, "INFO"), "warning": (13, "WARN"), "high": (17, "ERROR"), "critical": (21, "FATAL")}


def _check(response: httpx.Response) -> httpx.Response:
    if response.status_code >= 300:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:160]}")
    return response


def secrets_of(secret: str | None) -> dict[str, str]:
    """Grafana keeps several secrets (Loki, annotations, metrics) in one vault entry, as JSON."""
    try:
        value = json.loads(secret or "{}")
        return {k: str(v) for k, v in value.items() if v} if isinstance(value, dict) else {}
    except ValueError:
        return {}


# ---- Grafana ------------------------------------------------------------------------------------------

def loki_payload(event: dict[str, Any], labels: str) -> dict[str, Any]:
    stream = {"app": "borntoshare", "type": event["type"], "severity": event["severity"]}
    for pair in str(labels or "").split(","):
        key, _, value = pair.partition("=")
        if key.strip() and value.strip():
            stream[key.strip()] = value.strip()
    return {"streams": [{"stream": stream, "values": [[str(time.time_ns()), json.dumps(event, ensure_ascii=False, default=str)]]}]}


def annotation_payload(event: dict[str, Any], dashboard_uid: str | None) -> dict[str, Any]:
    body: dict[str, Any] = {"time": int(time.time() * 1000), "tags": ["borntoshare", event["type"], event["severity"]], "text": event["summary"]}
    if dashboard_uid:
        body["dashboardUID"] = dashboard_uid
    return body


def send_grafana(config: dict[str, Any], secret: str | None, event: dict[str, Any]) -> None:
    keys = secrets_of(secret)
    sent = False
    if config.get("loki_url"):
        auth = (config["loki_user"], keys.get("loki", "")) if config.get("loki_user") else None
        headers = {} if auth or not keys.get("loki") else {"Authorization": f"Bearer {keys['loki']}"}
        _check(httpx.post(config["loki_url"], json=loki_payload(event, config.get("labels", "")), auth=auth, headers=headers, timeout=TIMEOUT))
        sent = True
    if config.get("grafana_url") and keys.get("grafana") and event["type"] == "alerts":
        url = str(config["grafana_url"]).rstrip("/") + "/api/annotations"
        _check(httpx.post(url, json=annotation_payload(event, config.get("dashboard_uid")), headers={"Authorization": f"Bearer {keys['grafana']}"}, timeout=TIMEOUT))
        sent = True
    if not sent and event["type"] != "alerts":
        raise ValueError("No Loki URL")


# ---- OpenTelemetry -------------------------------------------------------------------------------------

def otel_headers(raw: str | None) -> dict[str, str]:
    """« Authorization=Bearer x;X-Scope=y » -> headers (kept in the vault)."""
    out: dict[str, str] = {}
    for pair in str(raw or "").replace("\n", ";").split(";"):
        key, _, value = pair.partition("=")
        if key.strip() and value.strip():
            out[key.strip()] = value.strip()
    return out


def otel_resource(config: dict[str, Any], service: str = "core-service") -> dict[str, Any]:
    attributes = {
        "service.name": service,
        "service.namespace": config.get("service_namespace") or "borntoshare",
        "deployment.environment": config.get("environment") or "production",
        "host.name": socket.gethostname(),
        "service.version": os.getenv("APP_VERSION", ""),
    }
    return {"attributes": [{"key": key, "value": {"stringValue": str(value)}} for key, value in attributes.items() if value]}


def _attr(key: str, value: Any) -> dict[str, Any]:
    if isinstance(value, bool):
        return {"key": key, "value": {"boolValue": value}}
    if isinstance(value, int):
        return {"key": key, "value": {"intValue": str(value)}}
    return {"key": key, "value": {"stringValue": str(value)}}


def otel_log_payload(config: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    number, text_severity = _OTEL_SEVERITY.get(event["severity"], (9, "INFO"))
    attributes = [_attr(f"b2s.{key}", event[key]) for key in ("type", "category", "action", "outcome", "actor", "target") if event.get(key) not in (None, "")]
    record = {"timeUnixNano": str(time.time_ns()), "severityNumber": number, "severityText": text_severity, "body": {"stringValue": event["summary"]}, "attributes": attributes}
    return {"resourceLogs": [{"resource": otel_resource(config), "scopeLogs": [{"scope": {"name": "borntoshare.events"}, "logRecords": [record]}]}]}


def otel_metrics_payload(config: dict[str, Any], figures: list[dict[str, Any]]) -> dict[str, Any]:
    now = str(time.time_ns())
    metrics: dict[str, dict[str, Any]] = {}
    for figure in figures:
        metric = metrics.setdefault(figure["name"], {"name": figure["name"], "description": figure["help"], "gauge": {"dataPoints": []}})
        metric["gauge"]["dataPoints"].append({"timeUnixNano": now, "asInt": str(figure["value"]), "attributes": [_attr(k, v) for k, v in figure["labels"].items()]})
    return {"resourceMetrics": [{"resource": otel_resource(config), "scopeMetrics": [{"scope": {"name": "borntoshare.platform"}, "metrics": list(metrics.values())}]}]}


def otel_traces_payload(config: dict[str, Any], spans: list[dict[str, Any]]) -> dict[str, Any]:
    return {"resourceSpans": [{"resource": otel_resource(config), "scopeSpans": [{"scope": {"name": "borntoshare.http"}, "spans": spans}]}]}


def otel_post(config: dict[str, Any], secret: str | None, signal: str, payload: dict[str, Any]) -> None:
    url = str(config.get("endpoint") or "").rstrip("/")
    if not url:
        raise ValueError("No OTLP endpoint")
    _check(httpx.post(f"{url}/v1/{signal}", json=payload, headers={"Content-Type": "application/json", **otel_headers(secret)}, timeout=TIMEOUT))


def send_otel(config: dict[str, Any], secret: str | None, event: dict[str, Any]) -> None:
    if config.get("logs", True):
        otel_post(config, secret, "logs", otel_log_payload(config, event))


# ---- ServiceNow ------------------------------------------------------------------------------------------

def _snow_auth(config: dict[str, Any], secret: str | None) -> tuple[dict[str, str], tuple[str, str] | None]:
    instance = str(config.get("instance_url") or "").rstrip("/")
    if config.get("auth") == "oauth":
        token = _check(httpx.post(f"{instance}/oauth_token.do", data={"grant_type": "client_credentials", "client_id": config.get("client_id", ""), "client_secret": secret or ""}, timeout=TIMEOUT)).json()
        return {"Authorization": f"Bearer {token['access_token']}"}, None
    return {}, (str(config.get("username") or ""), secret or "")


def incident_body(config: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    impact, urgency = _IMPACT.get(event["severity"], ("3", "3"))
    body = {
        "short_description": f"[BornToShare] {event['summary']}"[:160],
        "description": json.dumps({k: event.get(k) for k in ("summary", "action", "severity", "target", "at")}, ensure_ascii=False, indent=1, default=str),
        "correlation_id": str((event.get("context") or {}).get("alert_key") or event["action"])[:100],
        "correlation_display": "BornToShare",
        "impact": impact,
        "urgency": urgency,
        "category": config.get("category") or "software",
    }
    if config.get("assignment_group"):
        body["assignment_group"] = config["assignment_group"]
    if config.get("cmdb_ci"):
        body["cmdb_ci"] = config["cmdb_ci"]
    return body


def send_servicenow(config: dict[str, Any], secret: str | None, event: dict[str, Any]) -> None:
    instance = str(config.get("instance_url") or "").rstrip("/")
    if not instance:
        raise ValueError("No ServiceNow instance")
    headers, auth = _snow_auth(config, secret)
    headers["Accept"] = "application/json"
    table = f"{instance}/api/now/table/incident"
    correlation = str((event.get("context") or {}).get("alert_key") or event["action"])[:100]
    existing = _check(httpx.get(table, params={"sysparm_query": f"correlation_id={correlation}^active=true", "sysparm_fields": "sys_id,number", "sysparm_limit": 1}, headers=headers, auth=auth, timeout=TIMEOUT)).json().get("result") or []
    if event["type"] == "alerts":
        if existing:
            return  # the incident of this alert is already open: no duplicate
        _check(httpx.post(table, params={"sysparm_input_display_value": "true"}, json=incident_body(config, event), headers=headers, auth=auth, timeout=TIMEOUT))
    elif event["type"] == "alerts_resolved" and existing:
        _check(httpx.patch(f"{table}/{existing[0]['sys_id']}", json={"state": "6", "close_code": config.get("close_code") or "Resolved by caller", "close_notes": "Alerte fermée dans BornToShare."}, headers=headers, auth=auth, timeout=TIMEOUT))


def servicenow_check(config: dict[str, Any], secret: str | None) -> None:
    """Test of the connection: read one incident (rights on the table, authentication)."""
    instance = str(config.get("instance_url") or "").rstrip("/")
    headers, auth = _snow_auth(config, secret)
    _check(httpx.get(f"{instance}/api/now/table/incident", params={"sysparm_limit": 1, "sysparm_fields": "number"}, headers={**headers, "Accept": "application/json"}, auth=auth, timeout=TIMEOUT))


def _verify(config: dict[str, Any], ca_file: str) -> bool | str:
    mode = str(config.get("verify") or "public")
    if mode == "none":
        return False
    return f"/etc/b2s/certs/{ca_file}" if mode == "file" else True


def _when(event: dict[str, Any]) -> datetime:
    try:
        return datetime.fromisoformat(str(event.get("at") or "").replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


# ---- OpenSearch ---------------------------------------------------------------------------------------

def opensearch_index(config: dict[str, Any], event: dict[str, Any]) -> str:
    """The index of an event: the name given, with {yyyy}, {MM}, {dd} replaced by its date (one index a month: borntoshare-{yyyy}.{MM})."""
    at = _when(event)
    name = str(config.get("index") or "borntoshare-{yyyy}.{MM}")
    return name.replace("{yyyy}", f"{at.year:04d}").replace("{MM}", f"{at.month:02d}").replace("{dd}", f"{at.day:02d}").lower()


def opensearch_document(event: dict[str, Any]) -> dict[str, Any]:
    return {"@timestamp": event.get("at"), "source": "borntoshare", "host": socket.gethostname(), **event}


def send_opensearch(config: dict[str, Any], secret: str | None, event: dict[str, Any]) -> None:
    url = f"{str(config.get('url') or '').rstrip('/')}/{quote(opensearch_index(config, event))}/_doc"
    auth = (str(config["username"]), secret or "") if config.get("username") else None
    _check(httpx.post(url, json=opensearch_document(event), auth=auth, timeout=TIMEOUT, verify=_verify(config, "opensearch-ca.pem")))


# ---- RabbitMQ -----------------------------------------------------------------------------------------

def rabbitmq_routing_key(config: dict[str, Any], event: dict[str, Any]) -> str:
    """borntoshare.<audit|alerts>.<family>: a queue bound to « borntoshare.alerts.# » gets the alerts only."""
    prefix = str(config.get("routing_prefix") or "borntoshare").strip(".")
    return f"{prefix}.{event.get('type') or 'audit'}.{event.get('category') or 'other'}"


def send_rabbitmq(config: dict[str, Any], secret: str | None, event: dict[str, Any]) -> None:
    base = str(config.get("url") or "").rstrip("/")
    vhost = quote(str(config.get("vhost") or "/"), safe="")
    exchange = quote(str(config.get("exchange") or "amq.topic"), safe="")
    body = {"properties": {"content_type": "application/json", "delivery_mode": 2, "app_id": "borntoshare"},
            "routing_key": rabbitmq_routing_key(config, event), "payload": json.dumps(event, default=str), "payload_encoding": "string"}
    response = _check(httpx.post(f"{base}/api/exchanges/{vhost}/{exchange}/publish", json=body, auth=(str(config.get("username") or ""), secret or ""),
                                 timeout=TIMEOUT, verify=_verify(config, "rabbitmq-ca.pem")))
    if not response.json().get("routed"):
        raise RuntimeError(f"Message accepté mais distribué à aucune file (exchange {config.get('exchange') or 'amq.topic'}, clé {body['routing_key']})")


# ---- MinIO / S3 ---------------------------------------------------------------------------------------

def _sign(key: bytes, message: str) -> bytes:
    return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()


def s3_headers(method: str, url: str, body: bytes, access_key: str, secret_key: str, region: str, now: datetime) -> dict[str, str]:
    """Headers of a request signed with AWS Signature Version 4 (service s3), as MinIO and every S3 store check them."""
    parsed = urlparse(url)
    amz_date, day = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
    payload = hashlib.sha256(body).hexdigest()
    headers = {"host": parsed.netloc, "x-amz-content-sha256": payload, "x-amz-date": amz_date}
    signed = ";".join(sorted(headers))
    canonical = "\n".join([method, parsed.path or "/", parsed.query, "".join(f"{key}:{headers[key]}\n" for key in sorted(headers)), signed, payload])
    scope = f"{day}/{region}/s3/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode("utf-8")).hexdigest()])
    key = _sign(_sign(_sign(_sign(f"AWS4{secret_key}".encode("utf-8"), day), region), "s3"), "aws4_request")
    signature = hmac.new(key, to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
    return {**headers, "authorization": f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, SignedHeaders={signed}, Signature={signature}"}


def s3_object_key(config: dict[str, Any], event: dict[str, Any]) -> str:
    """<prefix>/<audit|alerts>/<yyyy>/<MM>/<dd>/<HHMMSS>-<id>.json: one object per event, by day."""
    at = _when(event)
    prefix = str(config.get("prefix") or "borntoshare").strip("/")
    return f"{prefix}/{event.get('type') or 'audit'}/{at:%Y/%m/%d}/{at:%H%M%S}-{uuid.uuid4().hex[:12]}.json"


def send_minio(config: dict[str, Any], secret: str | None, event: dict[str, Any]) -> None:
    base = str(config.get("endpoint") or "").rstrip("/")
    key = s3_object_key(config, event)
    url = f"{base}/{quote(str(config.get('bucket') or ''))}/{quote(key)}"
    body = json.dumps(event, default=str).encode("utf-8")
    headers = s3_headers("PUT", url, body, str(config.get("access_key") or ""), secret or "", str(config.get("region") or "us-east-1"),
                         datetime.now(timezone.utc))
    _check(httpx.put(url, content=body, headers={**headers, "content-type": "application/json"}, timeout=TIMEOUT,
                     verify=_verify(config, "minio-ca.pem")))
