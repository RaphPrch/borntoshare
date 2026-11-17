"""OpenSearch, RabbitMQ, MinIO (S3) and HashiCorp Vault: what each connector sends or reads, without the servers
(the servers themselves are tried by the integration run against real containers, docs/extensions.md)."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import pytest

from app.services import extension_senders as senders
from app.services import vault

EVENT = {"type": "alerts", "category": "folders", "action": "governance_alert.created", "summary": "x", "severity": "high",
         "at": "2026-11-17T10:41:55+00:00"}


class _Response:
    def __init__(self, status=200, body=None):
        self.status_code, self._body, self.text, self.headers = status, body or {}, "", {"content-type": "application/json"}

    def json(self):
        return self._body


def test_opensearch_one_document_in_a_dated_index(monkeypatch):
    sent = {}
    monkeypatch.setattr(senders.httpx, "post", lambda url, **kw: sent.update(url=url, **kw) or _Response(201))
    senders.send_opensearch({"url": "https://search:9200/", "index": "B2S-{yyyy}.{MM}", "username": "b2s"}, "pw", EVENT)
    assert sent["url"] == "https://search:9200/b2s-2026.11/_doc"
    assert sent["json"]["@timestamp"] == EVENT["at"] and sent["json"]["action"] == EVENT["action"] and sent["auth"] == ("b2s", "pw")


def test_rabbitmq_routing_key_and_a_message_routed_nowhere_is_a_failure(monkeypatch):
    sent = {}
    monkeypatch.setattr(senders.httpx, "post", lambda url, **kw: sent.update(url=url, **kw) or _Response(200, {"routed": True}))
    senders.send_rabbitmq({"url": "http://mq:15672", "vhost": "/", "exchange": "b2s.events", "username": "b2s"}, "pw", EVENT)
    assert sent["url"] == "http://mq:15672/api/exchanges/%2F/b2s.events/publish"
    assert sent["json"]["routing_key"] == "borntoshare.alerts.folders" and sent["json"]["properties"]["delivery_mode"] == 2
    monkeypatch.setattr(senders.httpx, "post", lambda url, **kw: _Response(200, {"routed": False}))
    with pytest.raises(RuntimeError, match="aucune file"):
        senders.send_rabbitmq({"url": "http://mq:15672"}, "pw", EVENT)


def test_minio_object_by_day_and_signature_v4(monkeypatch):
    assert senders.s3_object_key({"prefix": "/archive/"}, EVENT).startswith("archive/alerts/2026/11/17/104155-")
    now = datetime(2026, 11, 17, 10, 41, 55, tzinfo=timezone.utc)
    headers = senders.s3_headers("PUT", "http://minio:9000/b2s/archive/x.json", b"{}", "AK", "SK", "us-east-1", now)
    assert headers["x-amz-date"] == "20261117T104155Z" and headers["x-amz-content-sha256"] == hashlib.sha256(b"{}").hexdigest()
    assert headers["authorization"].startswith("AWS4-HMAC-SHA256 Credential=AK/20261117/us-east-1/s3/aws4_request, "
                                               "SignedHeaders=host;x-amz-content-sha256;x-amz-date, Signature=")
    # Same request, same signature; another secret, another one
    assert headers == senders.s3_headers("PUT", "http://minio:9000/b2s/archive/x.json", b"{}", "AK", "SK", "us-east-1", now)
    assert headers["authorization"] != senders.s3_headers("PUT", "http://minio:9000/b2s/archive/x.json", b"{}", "AK", "other", "us-east-1", now)["authorization"]


def test_vault_reference_is_read_in_kv2_and_kept_a_minute(monkeypatch):
    vault.forget()
    calls = []

    def get(url, **kw):
        calls.append((url, kw["headers"].get("X-Vault-Token")))
        return _Response(200, {"data": {"data": {"password": "s3cret"}}})

    monkeypatch.setattr(vault.httpx, "get", get)
    config = {"url": "https://vault:8200", "auth": "token"}
    assert vault.read(config, "tok", "vault://secret/borntoshare/svc-sync#password") == "s3cret"
    assert vault.read(config, "tok", "vault://secret/borntoshare/svc-sync#password") == "s3cret"
    assert calls == [("https://vault:8200/v1/secret/data/borntoshare/svc-sync", "tok")]


@pytest.mark.parametrize("reference", ["vault://secret#k", "vault://secret/x", "vault://secret/../x#k"])
def test_vault_reference_refused(reference):
    with pytest.raises(vault.VaultError):
        vault.parse(reference)


def test_vault_missing_key_and_forbidden_path_are_said(monkeypatch):
    vault.forget()
    monkeypatch.setattr(vault.httpx, "get", lambda url, **kw: _Response(200, {"data": {"data": {"user": "x"}}}))
    with pytest.raises(vault.VaultError, match="Clé « password » absente"):
        vault.read({"url": "https://v"}, "t", "vault://secret/a#password")
    monkeypatch.setattr(vault.httpx, "get", lambda url, **kw: _Response(403))
    with pytest.raises(vault.VaultError, match="refusée"):
        vault.read({"url": "https://v"}, "t", "vault://secret/b#password")


def test_vault_approle_login_is_kept_until_near_its_end(monkeypatch):
    vault.forget()
    logins = []
    monkeypatch.setattr(vault.httpx, "post", lambda url, **kw: logins.append(kw["json"]) or _Response(200, {"auth": {"client_token": "t1", "lease_duration": 3600}}))
    config = {"url": "https://v", "auth": "approle", "role_id": "rid"}
    assert vault.token_for(config, "sid") == "t1" and vault.token_for(config, "sid") == "t1"
    assert logins == [{"role_id": "rid", "secret_id": "sid"}]


def test_a_secret_that_cannot_be_read_is_a_failed_delivery_never_a_crash(monkeypatch):
    from app.services import extensions as ext

    recorded = []

    class _Db:
        def close(self):
            pass

    row = {"key": "rabbitmq", "enabled": True, "config": {}, "secret_ref": "sm://extension/rabbitmq", "routes": {}}
    monkeypatch.setattr(ext, "load", lambda db: [row])
    monkeypatch.setattr("app.core.db.SessionLocal", lambda: _Db())

    def unreadable(db, ref):
        raise RuntimeError("Secret absent de Vault : secret/borntoshare/nothing")

    monkeypatch.setattr("app.services.secret_store.resolve", unreadable)
    monkeypatch.setattr(ext, "record", lambda db, key, event, status, detail, attempts, latency: recorded.append((status, detail)))
    monkeypatch.setattr(ext, "deliver", lambda *a: (_ for _ in ()).throw(AssertionError("nothing sent without its secret")))
    ext._send_with_retries("rabbitmq", EVENT)
    assert recorded == [("failed", "Secret illisible : Secret absent de Vault : secret/borntoshare/nothing")]
