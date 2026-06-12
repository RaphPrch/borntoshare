from __future__ import annotations

import asyncio
import pytest
from types import SimpleNamespace

from fastapi import HTTPException

from app.api import provisioning as api


def test_create_access_profile_happy_path(monkeypatch) -> None:
    calls = {"queue": 0}

    async def _fake_dal_get(path: str, timeout: int = 5):
        if path == "/api/internal/provisioning/storage-root-access-profiles?storage_root_id=10&access_level_code=READ":
            return []
        if path == "/api/internal/provisioning/jobs/by-profile/77":
            raise HTTPException(status_code=404, detail="Provisioning job not found")
        assert path == "/api/internal/provisioning/storage-roots/10/context"
        return {
            "storage_root_id": 10,
            "storage_endpoint_id": 2,
            "identity_source_id": 9,
            "zone_id": 3,
            "root_path": r"\\srv\share\finance",
            "identity_source_kind": "AD",
            "write_enabled": 1,
            "secret_ref": "sm://ad/writer",
            "effective_group_ou_dn": "OU=Groups,DC=corp,DC=local",
            "default_group_ou_dn": "OU=Groups,DC=corp,DC=local",
            "domain_name": "corp.local",
        }

    async def _fake_dal_post(path: str, payload: dict, timeout: int = 5):
        if path == "/api/naming-policies/preview":
            assert payload["perm"] == "RX"
            assert payload["storage_root_id"] == 10
            assert payload["storage_endpoint_id"] == 2
            return {"samAccountName": "B2S_FINANCE_READ"}
        if path == "/api/internal/provisioning/storage-root-access-profiles":
            return {
                "created": True,
                "data": {
                    "id": 77,
                    "access_level_code": payload.get("access_level_code"),
                    "status": "PENDING",
                },
            }
        if path == "/api/internal/provisioning/storage-root-access-profiles/77/queue":
            return {"ok": True}
        if path == "/api/internal/provisioning/jobs":
            return {"created": True, "data": {"id": 501}}
        raise AssertionError(f"unexpected DAL POST path: {path}")

    class _FakeActor:
        @staticmethod
        def send(job_id: int):
            calls["queue"] += 1
            assert job_id == 501

    monkeypatch.setattr(api, "dal_get", _fake_dal_get)
    monkeypatch.setattr(api, "dal_post", _fake_dal_post)
    monkeypatch.setattr(api, "run_provisioning_job", _FakeActor())

    payload = api.AccessProfileCreateIn(access_level="READ", rights=[])
    out = asyncio.run(api.create_storage_root_access_profile(10, payload))

    body = out["data"]
    assert body["id"] == 77
    assert body["access_level"] == "READ"
    assert body["status"] == "QUEUED"
    assert calls["queue"] == 1


def test_create_access_profile_handles_naming_preview_data_envelope(monkeypatch) -> None:
    calls = {"queue": 0}

    async def _fake_dal_get(path: str, timeout: int = 5):
        if path == "/api/internal/provisioning/storage-root-access-profiles?storage_root_id=10&access_level_code=READ":
            return []
        if path == "/api/internal/provisioning/jobs/by-profile/77":
            raise HTTPException(status_code=404, detail="Provisioning job not found")
        assert path == "/api/internal/provisioning/storage-roots/10/context"
        return {
            "storage_root_id": 10,
            "storage_endpoint_id": 2,
            "identity_source_id": 9,
            "zone_id": 3,
            "root_path": r"\\srv\share\finance",
            "identity_source_kind": "AD",
            "write_enabled": 1,
            "secret_ref": "sm://ad/writer",
            "effective_group_ou_dn": "OU=Groups,DC=corp,DC=local",
            "default_group_ou_dn": "OU=Groups,DC=corp,DC=local",
            "domain_name": "corp.local",
        }

    async def _fake_dal_post(path: str, payload: dict, timeout: int = 5):
        if path == "/api/naming-policies/preview":
            assert payload["perm"] == "RX"
            assert payload["storage_root_id"] == 10
            assert payload["storage_endpoint_id"] == 2
            return {"data": {"samAccountName": "B2S_FINANCE_READ"}, "meta": {}}
        if path == "/api/internal/provisioning/storage-root-access-profiles":
            return {
                "created": True,
                "data": {
                    "id": 77,
                    "access_level_code": payload.get("access_level_code"),
                    "status": "PENDING",
                },
            }
        if path == "/api/internal/provisioning/storage-root-access-profiles/77/queue":
            return {"ok": True}
        if path == "/api/internal/provisioning/jobs":
            return {"created": True, "data": {"id": 501}}
        raise AssertionError(f"unexpected DAL POST path: {path}")

    class _FakeActor:
        @staticmethod
        def send(job_id: int):
            calls["queue"] += 1
            assert job_id == 501

    monkeypatch.setattr(api, "dal_get", _fake_dal_get)
    monkeypatch.setattr(api, "dal_post", _fake_dal_post)
    monkeypatch.setattr(api, "run_provisioning_job", _FakeActor())

    payload = api.AccessProfileCreateIn(access_level="READ", rights=[])
    out = asyncio.run(api.create_storage_root_access_profile(10, payload))

    body = out["data"]
    assert body["id"] == 77
    assert body["access_level"] == "READ"
    assert body["status"] == "QUEUED"
    assert calls["queue"] == 1


def test_create_access_profile_returns_structured_error_when_naming_preview_empty(monkeypatch) -> None:
    async def _fake_dal_get(path: str, timeout: int = 5):
        if path == "/api/internal/provisioning/storage-root-access-profiles?storage_root_id=10&access_level_code=READ":
            return []
        assert path == "/api/internal/provisioning/storage-roots/10/context"
        return {
            "storage_root_id": 10,
            "storage_endpoint_id": 2,
            "identity_source_id": 9,
            "zone_id": 3,
            "root_path": r"\\srv\share\finance",
            "identity_source_kind": "AD",
            "write_enabled": 1,
            "secret_ref": "sm://ad/writer",
            "effective_group_ou_dn": "OU=Groups,DC=corp,DC=local",
            "default_group_ou_dn": "OU=Groups,DC=corp,DC=local",
            "domain_name": "corp.local",
        }

    async def _fake_dal_post(path: str, payload: dict, timeout: int = 5):
        if path == "/api/naming-policies/preview":
            return {"data": {}, "meta": {}}
        raise AssertionError(f"unexpected DAL POST path: {path}")

    monkeypatch.setattr(api, "dal_get", _fake_dal_get)
    monkeypatch.setattr(api, "dal_post", _fake_dal_post)

    payload = api.AccessProfileCreateIn(access_level="READ", rights=[])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(api.create_storage_root_access_profile(10, payload))

    assert exc.value.status_code == 422
    detail = exc.value.detail if isinstance(exc.value.detail, dict) else {}
    assert detail.get("code") == "NAMING_PREVIEW_EMPTY"
    details = detail.get("details") if isinstance(detail.get("details"), dict) else {}
    assert details.get("storage_root_id") == 10
    assert details.get("access_level") == "READ"


def test_complete_job_create_group_uses_complete_and_apply(monkeypatch) -> None:
    post_calls: list[tuple[str, dict]] = []

    async def _fake_dal_get(path: str):
        assert path == "/api/internal/provisioning/jobs/by-correlation/corr_ok"
        return {
            "id": 501,
            "storage_root_access_profile_id": 77,
            "identity_source_id": 9,
            "payload_json": {
                "action": "ensure_ad_group",
                "payload": {"zone_id": 3, "storage_root_id": 10},
            },
        }

    async def _fake_dal_post(path: str, payload: dict, timeout: int = 5):
        post_calls.append((path, payload))
        return {"ok": True}

    monkeypatch.setattr(api, "dal_get", _fake_dal_get)
    monkeypatch.setattr(api, "dal_post", _fake_dal_post)

    payload = api.ProvisioningCompleteIn(stage="AD_GROUP_ENSURE", status="SUCCESS", group_dn="CN=grp,OU=Groups,DC=corp,DC=local")
    out = asyncio.run(api.complete_provisioning_job("corr_ok", payload, request=None))

    assert out["data"]["ok"] is True
    assert post_calls[0][0] == "/api/internal/provisioning/jobs/501/complete-and-apply"
    assert post_calls[0][1]["outcome"] == "SUCCEEDED"
    assert post_calls[0][1]["profile_id"] == 77


def test_complete_job_rejects_legacy_flat_payload_envelope(monkeypatch) -> None:
    async def _fake_dal_get(path: str):
        assert path == "/api/internal/provisioning/jobs/by-correlation/corr_bad"
        return {
            "id": 501,
            "storage_root_access_profile_id": 77,
            "identity_source_id": 9,
            "payload_json": {"zone_id": 3, "storage_root_id": 10},
        }

    async def _fake_dal_post(path: str, payload: dict, timeout: int = 5):  # pragma: no cover - guard
        _ = path, payload, timeout
        raise AssertionError("dal_post must not be called on invalid payload envelope")

    monkeypatch.setattr(api, "dal_get", _fake_dal_get)
    monkeypatch.setattr(api, "dal_post", _fake_dal_post)

    payload = api.ProvisioningCompleteIn(stage="AD_GROUP_ENSURE", status="SUCCESS", group_dn="CN=grp,OU=Groups,DC=corp,DC=local")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(api.complete_provisioning_job("corr_bad", payload, request=None))

    assert exc.value.status_code == 422
    detail = exc.value.detail if isinstance(exc.value.detail, dict) else {}
    assert detail.get("code") == "INVALID_JOB_PAYLOAD_ENVELOPE"


def test_complete_job_non_profile_uses_job_fail(monkeypatch) -> None:
    post_calls: list[tuple[str, dict]] = []

    async def _fake_dal_get(path: str):
        assert path == "/api/internal/provisioning/jobs/by-correlation/corr_fail"
        return {
            "id": 501,
            "storage_root_access_profile_id": 0,
            "identity_source_id": 9,
        }

    async def _fake_dal_post(path: str, payload: dict, timeout: int = 5):
        post_calls.append((path, payload))
        return {"ok": True}

    monkeypatch.setattr(api, "dal_get", _fake_dal_get)
    monkeypatch.setattr(api, "dal_post", _fake_dal_post)

    payload = api.ProvisioningCompleteIn(stage="AD_GROUP_ENSURE", status="FAILED", error_code="AD_ERR", error_message="boom")
    out = asyncio.run(api.complete_provisioning_job("corr_fail", payload, request=None))

    assert out["data"]["ok"] is True
    assert post_calls[0][0] == "/api/internal/provisioning/jobs/501/fail"
    assert post_calls[0][1]["error_code"] == "AD_ERR"


def test_retry_failed_job_creates_new_job_and_queues(monkeypatch) -> None:
    post_calls: list[tuple[str, dict]] = []
    log_calls: list[str] = []

    async def _fake_dal_get(path: str, timeout: int = 5):
        if path == "/api/internal/provisioning/jobs/by-correlation/corr_failed":
            return {
                "id": 501,
                "status": "FAILED",
                "attempt_count": 1,
                "job_type": "AD_GROUP_ENSURE",
                "identity_source_id": 9,
                "storage_root_access_profile_id": 77,
                "payload_json": {
                    "action": "ensure_ad_group",
                    "payload": {"storage_root_id": 10, "group_name": "B2S_FINANCE_READ"},
                },
            }
        if path == "/api/internal/provisioning/storage-root-access-profiles/77":
            return {"id": 77, "status": "FAILED", "attempt_count": 1}
        if path == "/api/internal/provisioning/storage-roots/10/context":
            return {
                "zone_id": 3,
                "storage_endpoint_id": 2,
                "identity_source_id": 9,
                "identity_source_kind": "AD",
                "identity_source_host": "dc.corp.local",
                "identity_source_port": 389,
                "identity_source_protocol": "ldap",
                "identity_source_bind_dn": "CN=svc,DC=corp,DC=local",
                "identity_source_base_dn": "DC=corp,DC=local",
                "domain_name": "corp.local",
                "effective_group_ou_dn": "OU=Groups,DC=corp,DC=local",
                "secret_ref": "sm://ad/writer",
            }
        raise AssertionError(path)

    async def _fake_dal_post(path: str, payload: dict, timeout: int = 5):
        post_calls.append((path, payload))
        if path == "/api/internal/provisioning/jobs":
            return {"created": True, "data": {"id": 777}}
        return {"ok": True}

    queue_calls = {"count": 0}

    class _FakeActor:
        @staticmethod
        def send(job_id: int):
            queue_calls["count"] += 1
            assert job_id == 777

    def _fake_log_event(**kwargs):
        log_calls.append(str(kwargs.get("action") or ""))

    monkeypatch.setattr(api, "dal_get", _fake_dal_get)
    monkeypatch.setattr(api, "dal_post", _fake_dal_post)
    monkeypatch.setattr(api, "run_provisioning_job", _FakeActor())
    monkeypatch.setattr(api, "log_event", _fake_log_event)

    out = asyncio.run(api.retry_failed_provisioning_job("corr_failed", request=None))
    body = out["data"]
    assert body["ok"] is True
    assert body["status"] == "QUEUED"
    assert body["attempt_count"] == 2
    assert body["backoff_minutes"] == 5
    assert body["correlation_id"] == "corr_failed-retry-2"
    assert post_calls[0][0] == "/api/internal/provisioning/jobs"
    assert post_calls[0][1]["correlation_id"] == "corr_failed-retry-2"
    metrics = post_calls[0][1]["metrics_json"]
    assert metrics["retry_attempt"] == 2
    assert metrics["retry_backoff_minutes"] == 5
    assert metrics["source_job_attempt"] == 1
    assert metrics["source_profile_attempt"] == 1
    assert queue_calls["count"] == 1
    assert "access_profile_provisioning_retry" in log_calls


def test_retry_failed_job_uses_max_attempt_between_job_and_profile(monkeypatch) -> None:
    post_calls: list[tuple[str, dict]] = []

    async def _fake_dal_get(path: str, timeout: int = 5):
        if path == "/api/internal/provisioning/jobs/by-correlation/corr_failed":
            return {
                "id": 501,
                "status": "FAILED",
                "attempt_count": 1,
                "job_type": "AD_GROUP_ENSURE",
                "identity_source_id": 9,
                "storage_root_access_profile_id": 77,
                "payload_json": {
                    "action": "ensure_ad_group",
                    "payload": {"storage_root_id": 10, "group_name": "B2S_FINANCE_READ"},
                },
            }
        if path == "/api/internal/provisioning/storage-root-access-profiles/77":
            return {"id": 77, "status": "FAILED", "attempt_count": 4}
        if path == "/api/internal/provisioning/storage-roots/10/context":
            return {
                "zone_id": 3,
                "storage_endpoint_id": 2,
                "identity_source_id": 9,
                "identity_source_kind": "AD",
                "identity_source_host": "dc.corp.local",
                "identity_source_port": 389,
                "identity_source_protocol": "ldap",
                "identity_source_bind_dn": "CN=svc,DC=corp,DC=local",
                "identity_source_base_dn": "DC=corp,DC=local",
                "domain_name": "corp.local",
                "effective_group_ou_dn": "OU=Groups,DC=corp,DC=local",
                "secret_ref": "sm://ad/writer",
            }
        raise AssertionError(path)

    async def _fake_dal_post(path: str, payload: dict, timeout: int = 5):
        post_calls.append((path, payload))
        if path == "/api/internal/provisioning/jobs":
            return {"created": True, "data": {"id": 778}}
        return {"ok": True}

    class _FakeActor:
        @staticmethod
        def send(job_id: int):
            assert job_id == 778

    monkeypatch.setattr(api, "dal_get", _fake_dal_get)
    monkeypatch.setattr(api, "dal_post", _fake_dal_post)
    monkeypatch.setattr(api, "run_provisioning_job", _FakeActor())
    monkeypatch.setattr(api, "log_event", lambda **kwargs: None)

    out = asyncio.run(api.retry_failed_provisioning_job("corr_failed", request=None))
    body = out["data"]
    assert body["ok"] is True
    assert body["status"] == "QUEUED"
    assert body["attempt_count"] == 5
    assert body["backoff_minutes"] == 60
    assert body["correlation_id"] == "corr_failed-retry-5"
    assert post_calls[0][0] == "/api/internal/provisioning/jobs"
    assert post_calls[0][1]["correlation_id"] == "corr_failed-retry-5"


def test_retry_failed_job_rejects_when_attempt_limit_reached(monkeypatch) -> None:
    async def _fake_dal_get(path: str, timeout: int = 5):
        if path == "/api/internal/provisioning/jobs/by-correlation/corr_failed":
            return {
                "id": 501,
                "status": "FAILED",
                "attempt_count": 5,
                "job_type": "AD_GROUP_ENSURE",
                "identity_source_id": 9,
                "storage_root_access_profile_id": 77,
                "payload_json": {
                    "action": "ensure_ad_group",
                    "payload": {"storage_root_id": 10, "group_name": "B2S_FINANCE_READ"},
                },
            }
        if path == "/api/internal/provisioning/storage-root-access-profiles/77":
            return {"id": 77, "status": "FAILED", "attempt_count": 5}
        if path == "/api/internal/provisioning/storage-roots/10/context":
            return {
                "zone_id": 3,
                "identity_source_id": 9,
                "identity_source_kind": "AD",
                "secret_ref": "sm://ad/writer",
                "effective_group_ou_dn": "OU=Groups,DC=corp,DC=local",
            }
        raise AssertionError(path)

    async def _fake_dal_post(path: str, payload: dict, timeout: int = 5):  # pragma: no cover
        raise AssertionError(path)

    monkeypatch.setattr(api, "dal_get", _fake_dal_get)
    monkeypatch.setattr(api, "dal_post", _fake_dal_post)

    with pytest.raises(api.HTTPException) as exc:
        asyncio.run(api.retry_failed_provisioning_job("corr_failed", request=None))

    assert exc.value.status_code == 409
    detail = exc.value.detail if isinstance(exc.value.detail, dict) else {}
    assert detail.get("error_code") == "GOVERNANCE_RETRY_LIMIT_REACHED"


def test_retry_failed_job_reads_group_name_from_envelope_payload(monkeypatch) -> None:
    post_calls: list[tuple[str, dict]] = []

    async def _fake_dal_get(path: str, timeout: int = 5):
        if path == "/api/internal/provisioning/jobs/by-correlation/corr_failed":
            return {
                "id": 501,
                "status": "FAILED",
                "attempt_count": 1,
                "job_type": "AD_GROUP_ENSURE",
                "identity_source_id": 9,
                "storage_root_access_profile_id": 77,
                "payload_json": {
                    "action": "ensure_ad_group",
                    "payload": {
                        "storage_root_id": 10,
                        "group_name": "B2S_FINANCE_READ",
                    },
                },
            }
        if path == "/api/internal/provisioning/storage-root-access-profiles/77":
            return {"id": 77, "status": "FAILED", "attempt_count": 1}
        if path == "/api/internal/provisioning/storage-roots/10/context":
            return {
                "zone_id": 3,
                "storage_endpoint_id": 2,
                "identity_source_id": 9,
                "identity_source_kind": "AD",
                "identity_source_host": "dc.corp.local",
                "identity_source_port": 389,
                "identity_source_protocol": "ldap",
                "identity_source_bind_dn": "CN=svc,DC=corp,DC=local",
                "identity_source_base_dn": "DC=corp,DC=local",
                "domain_name": "corp.local",
                "effective_group_ou_dn": "OU=Groups,DC=corp,DC=local",
                "secret_ref": "sm://ad/writer",
            }
        raise AssertionError(path)

    async def _fake_dal_post(path: str, payload: dict, timeout: int = 5):
        post_calls.append((path, payload))
        if path == "/api/internal/provisioning/jobs":
            return {"created": True, "data": {"id": 779}}
        return {"ok": True}

    class _FakeActor:
        @staticmethod
        def send(job_id: int):
            assert job_id == 779

    monkeypatch.setattr(api, "dal_get", _fake_dal_get)
    monkeypatch.setattr(api, "dal_post", _fake_dal_post)
    monkeypatch.setattr(api, "run_provisioning_job", _FakeActor())
    monkeypatch.setattr(api, "log_event", lambda **kwargs: None)

    out = asyncio.run(api.retry_failed_provisioning_job("corr_failed", request=None))
    body = out["data"]
    assert body["ok"] is True
    assert body["status"] == "QUEUED"
    assert body["attempt_count"] == 2
    assert body["backoff_minutes"] == 5
    assert post_calls[0][0] == "/api/internal/provisioning/jobs"
    posted_payload = post_calls[0][1]["payload_json"]
    assert posted_payload["secret_ref"] == "sm://ad/writer"
    assert posted_payload["payload"]["secret_ref"] == "sm://ad/writer"
    metrics = post_calls[0][1]["metrics_json"]
    assert metrics["retry_attempt"] == 2
    assert metrics["retry_backoff_minutes"] == 5


def test_ensure_ad_group_via_name_uses_payload_secret_ref_and_returns_202(monkeypatch) -> None:
    post_calls: list[tuple[str, dict]] = []
    queue_calls = {"count": 0}
    log_calls: list[str] = []

    async def _fake_dal_get(path: str, timeout: int = 5):
        raise AssertionError(path)

    async def _fake_dal_post(path: str, payload: dict, timeout: int = 5):
        post_calls.append((path, payload))
        if path == "/api/internal/provisioning/jobs":
            return {"created": True, "data": {"id": 9901}}
        raise AssertionError(path)

    class _FakeActor:
        @staticmethod
        def send(job_id: int):
            queue_calls["count"] += 1
            assert job_id == 9901

    def _fake_log_event(**kwargs):
        log_calls.append(str(kwargs.get("action") or ""))

    monkeypatch.setattr(api, "dal_get", _fake_dal_get)
    monkeypatch.setattr(api, "dal_post", _fake_dal_post)
    monkeypatch.setattr(api, "run_provisioning_job", _FakeActor())
    monkeypatch.setattr(api, "log_event", _fake_log_event)

    payload = api.EnsureAdGroupIn(
        group_name="B2S_FINANCE_READ",
        target_ou_dn="OU=Groups,DC=corp,DC=local",
        secret_ref="sm://ad/writer",
    )
    response = SimpleNamespace(status_code=None)
    out = asyncio.run(api.ensure_ad_group_via_name(payload=payload, request=None, response=response))

    body = out["data"]
    assert body["ok"] is True
    assert body["status"] == "QUEUED"
    assert response.status_code == 202
    assert post_calls[0][0] == "/api/internal/provisioning/jobs"
    assert post_calls[0][1]["payload_json"]["payload"]["secret_ref"] == "sm://ad/writer"
    assert queue_calls["count"] == 1
    assert "ad_group_ensure_queued" in log_calls


def test_ensure_ad_group_via_name_idempotent_with_profile(monkeypatch) -> None:
    async def _fake_dal_get(path: str, timeout: int = 5):
        if path == "/api/internal/provisioning/jobs/by-profile/77":
            return {"id": 701, "status": "RUNNING", "correlation_id": "corr-existing"}
        raise AssertionError(path)

    async def _fake_dal_post(path: str, payload: dict, timeout: int = 5):
        raise AssertionError(path)

    class _FakeActor:
        @staticmethod
        def send(job_id: int):
            raise AssertionError(job_id)

    monkeypatch.setattr(api, "dal_get", _fake_dal_get)
    monkeypatch.setattr(api, "dal_post", _fake_dal_post)
    monkeypatch.setattr(api, "run_provisioning_job", _FakeActor())

    payload = api.EnsureAdGroupIn(
        group_name="B2S_FINANCE_READ",
        target_ou_dn="OU=Groups,DC=corp,DC=local",
        secret_ref="sm://ad/writer",
        context=api.EnsureAdGroupContextIn(access_profile_id=77),
    )
    response = SimpleNamespace(status_code=None)
    out = asyncio.run(api.ensure_ad_group_via_name(payload=payload, request=None, response=response))

    body = out["data"]
    assert body["ok"] is True
    assert body["job_id"] == 701
    assert body["status"] == "RUNNING"
    assert body["correlation_id"] == "corr-existing"
    assert response.status_code == 202


def test_ensure_ad_group_via_name_uses_context_ou_fallbacks(monkeypatch) -> None:
    post_calls: list[tuple[str, dict]] = []
    queue_calls = {"count": 0}

    async def _fake_dal_get(path: str, timeout: int = 5):
        assert path == "/api/internal/provisioning/storage-roots/8010/context"
        return {
            "storage_root_id": 8010,
            "identity_source_id": 9,
            "domain_name": "corp.local",
            "secret_ref": "sm://ad/writer",
            "effective_group_ou_dn": None,
            "zone_default_group_ou_dn": "OU=ZoneGroups,DC=corp,DC=local",
            "default_group_ou_dn": "OU=DefaultGroups,DC=corp,DC=local",
        }

    async def _fake_dal_post(path: str, payload: dict, timeout: int = 5):
        post_calls.append((path, payload))
        if path == "/api/internal/provisioning/jobs":
            return {"created": True, "data": {"id": 9902}}
        raise AssertionError(path)

    class _FakeActor:
        @staticmethod
        def send(job_id: int):
            queue_calls["count"] += 1
            assert job_id == 9902

    monkeypatch.setattr(api, "dal_get", _fake_dal_get)
    monkeypatch.setattr(api, "dal_post", _fake_dal_post)
    monkeypatch.setattr(api, "run_provisioning_job", _FakeActor())
    monkeypatch.setattr(api, "log_event", lambda **kwargs: None)

    payload = api.EnsureAdGroupIn(
        group_name="B2S_FINANCE_READ",
        context=api.EnsureAdGroupContextIn(storage_root_id=8010),
    )
    out = asyncio.run(api.ensure_ad_group_via_name(payload=payload, request=None, response=None))

    assert out["data"]["ok"] is True
    assert post_calls[0][0] == "/api/internal/provisioning/jobs"
    assert post_calls[0][1]["payload_json"]["payload"]["target_ou_dn"] == "OU=ZoneGroups,DC=corp,DC=local"
    assert queue_calls["count"] == 1


def test_ensure_ad_group_via_name_falls_back_to_identity_default_ou(monkeypatch) -> None:
    post_calls: list[tuple[str, dict]] = []

    async def _fake_dal_get(path: str, timeout: int = 5):
        assert path == "/api/internal/provisioning/storage-roots/8010/context"
        return {
            "storage_root_id": 8010,
            "identity_source_id": 9,
            "domain_name": "corp.local",
            "secret_ref": "sm://ad/writer",
            "effective_group_ou_dn": None,
            "zone_default_group_ou_dn": None,
            "default_group_ou_dn": "OU=DefaultGroups,DC=corp,DC=local",
        }

    async def _fake_dal_post(path: str, payload: dict, timeout: int = 5):
        post_calls.append((path, payload))
        if path == "/api/internal/provisioning/jobs":
            return {"created": True, "data": {"id": 9903}}
        raise AssertionError(path)

    monkeypatch.setattr(api, "dal_get", _fake_dal_get)
    monkeypatch.setattr(api, "dal_post", _fake_dal_post)
    monkeypatch.setattr(api, "run_provisioning_job", type("_A", (), {"send": staticmethod(lambda _jid: None)})())
    monkeypatch.setattr(api, "log_event", lambda **kwargs: None)

    payload = api.EnsureAdGroupIn(
        group_name="B2S_FINANCE_READ",
        context=api.EnsureAdGroupContextIn(storage_root_id=8010),
    )
    out = asyncio.run(api.ensure_ad_group_via_name(payload=payload, request=None, response=None))

    assert out["data"]["ok"] is True
    assert post_calls[0][1]["payload_json"]["payload"]["target_ou_dn"] == "OU=DefaultGroups,DC=corp,DC=local"


def test_ensure_ad_group_via_name_rejects_invalid_target_ou_dn(monkeypatch) -> None:
    async def _fake_dal_get(path: str, timeout: int = 5):
        raise AssertionError(path)

    async def _fake_dal_post(path: str, payload: dict, timeout: int = 5):
        raise AssertionError(path)

    monkeypatch.setattr(api, "dal_get", _fake_dal_get)
    monkeypatch.setattr(api, "dal_post", _fake_dal_post)

    payload = api.EnsureAdGroupIn(
        group_name="B2S_FINANCE_READ",
        target_ou_dn="OU=Groups,INVALID",
        secret_ref="sm://ad/writer",
    )
    with pytest.raises(HTTPException) as exc:
        asyncio.run(api.ensure_ad_group_via_name(payload=payload, request=None, response=None))

    assert exc.value.status_code == 422
    detail = exc.value.detail if isinstance(exc.value.detail, dict) else {}
    assert detail.get("code") == "INVALID_TARGET_OU_DN"
    assert detail.get("target_ou_dn") == "OU=Groups,INVALID"


def test_ensure_ad_group_via_name_canonicalizes_repeated_dc_suffix(monkeypatch) -> None:
    post_calls: list[tuple[str, dict]] = []
    queue_calls = {"count": 0}

    async def _fake_dal_get(path: str, timeout: int = 5):
        raise AssertionError(path)

    async def _fake_dal_post(path: str, payload: dict, timeout: int = 5):
        post_calls.append((path, payload))
        if path == "/api/internal/provisioning/jobs":
            return {"created": True, "data": {"id": 9904}}
        raise AssertionError(path)

    class _FakeActor:
        @staticmethod
        def send(job_id: int):
            queue_calls["count"] += 1
            assert job_id == 9904

    monkeypatch.setattr(api, "dal_get", _fake_dal_get)
    monkeypatch.setattr(api, "dal_post", _fake_dal_post)
    monkeypatch.setattr(api, "run_provisioning_job", _FakeActor())
    monkeypatch.setattr(api, "log_event", lambda **kwargs: None)

    payload = api.EnsureAdGroupIn(
        group_name="B2S_FINANCE_READ",
        target_ou_dn="OU=CORP,DC=CORP,DC=LOCAL,DC=CORP,DC=LOCAL",
        secret_ref="sm://ad/writer",
    )
    out = asyncio.run(api.ensure_ad_group_via_name(payload=payload, request=None, response=None))

    assert out["data"]["ok"] is True
    assert post_calls[0][1]["payload_json"]["payload"]["target_ou_dn"] == "OU=CORP,DC=CORP,DC=LOCAL"
    assert queue_calls["count"] == 1


def test_ensure_ad_group_member_queues_membership_job(monkeypatch) -> None:
    created_calls: list[dict] = []

    async def _fake_resolve_identity_source_id_for_group_operation(*, identity_source_id: int | None, group_ref: str) -> int:
        assert identity_source_id is None
        assert group_ref == "CN=GRP_FINANCE_READ,OU=Groups,DC=corp,DC=local"
        return 9

    async def _fake_build_identity_source_capsule_context(identity_source_id: int) -> dict:
        assert identity_source_id == 9
        return {
            "identity_source_id": 9,
            "host": "dc01.corp.local",
            "bind_dn": "CN=svc,DC=corp,DC=local",
            "secret_ref": "sm://ad/writer",
            "protocol": "ldaps",
            "port": 636,
            "base_dn": "DC=corp,DC=local",
            "verify_tls": False,
            "timeout": 5,
        }

    async def _fake_create_and_publish_job(*, payload: dict, dal_post_fn=None, actor=None) -> dict:
        created_calls.append(payload)
        return {"job_id": 2201}

    monkeypatch.setattr(api, "_resolve_identity_source_id_for_group_operation", _fake_resolve_identity_source_id_for_group_operation)
    monkeypatch.setattr(api, "build_identity_source_capsule_context", _fake_build_identity_source_capsule_context)
    monkeypatch.setattr(api, "create_and_publish_job", _fake_create_and_publish_job)

    response = SimpleNamespace(status_code=None)
    payload = api.EnsureAdGroupMemberIn(
        group_ref="CN=GRP_FINANCE_READ,OU=Groups,DC=corp,DC=local",
        principal_username="jdoe",
    )
    out = asyncio.run(api.ensure_ad_group_member(payload=payload, request=None, response=response))

    body = out["data"]
    assert body["ok"] is True
    assert body["job_id"] == 2201
    assert body["status"] == "QUEUED"
    assert body["identity_source_id"] == 9
    assert response.status_code == 202
    assert created_calls[0]["job_type"] == "AD_GROUP_MEMBERSHIP"
    assert created_calls[0]["action"] == "ensure_ad_group_member"
    assert created_calls[0]["payload_json"]["payload"]["principal_username"] == "jdoe"


def test_remove_ad_group_member_queues_membership_remove_job(monkeypatch) -> None:
    created_calls: list[dict] = []

    async def _fake_resolve_identity_source_id_for_group_operation(*, identity_source_id: int | None, group_ref: str) -> int:
        assert identity_source_id == 9
        assert group_ref == "CN=GRP_FINANCE_READ,OU=Groups,DC=corp,DC=local"
        return 9

    async def _fake_build_identity_source_capsule_context(identity_source_id: int) -> dict:
        assert identity_source_id == 9
        return {
            "identity_source_id": 9,
            "host": "dc01.corp.local",
            "bind_dn": "CN=svc,DC=corp,DC=local",
            "secret_ref": "sm://ad/writer",
            "protocol": "ldaps",
            "port": 636,
            "base_dn": "DC=corp,DC=local",
            "verify_tls": False,
            "timeout": 5,
        }

    async def _fake_create_and_publish_job(*, payload: dict, dal_post_fn=None, actor=None) -> dict:
        created_calls.append(payload)
        return {"job_id": 2202}

    monkeypatch.setattr(api, "_resolve_identity_source_id_for_group_operation", _fake_resolve_identity_source_id_for_group_operation)
    monkeypatch.setattr(api, "build_identity_source_capsule_context", _fake_build_identity_source_capsule_context)
    monkeypatch.setattr(api, "create_and_publish_job", _fake_create_and_publish_job)

    response = SimpleNamespace(status_code=None)
    payload = api.RemoveAdGroupMemberIn(
        identity_source_id=9,
        group_ref="CN=GRP_FINANCE_READ,OU=Groups,DC=corp,DC=local",
        principal_dn="CN=John Doe,OU=Users,DC=corp,DC=local",
    )
    out = asyncio.run(api.remove_ad_group_member(payload=payload, request=None, response=response))

    body = out["data"]
    assert body["ok"] is True
    assert body["job_id"] == 2202
    assert body["status"] == "QUEUED"
    assert body["identity_source_id"] == 9
    assert response.status_code == 202
    assert created_calls[0]["job_type"] == "AD_GROUP_MEMBERSHIP_REMOVE"
    assert created_calls[0]["action"] == "remove_ad_group_member"
    assert created_calls[0]["payload_json"]["payload"]["principal_dn"] == "CN=John Doe,OU=Users,DC=corp,DC=local"


def test_discover_ad_group_users_recursive_queues_discovery_job(monkeypatch) -> None:
    created_calls: list[dict] = []

    async def _fake_resolve_identity_source_id_for_group_operation(*, identity_source_id: int | None, group_ref: str) -> int:
        assert identity_source_id == 9
        assert group_ref == "CN=GRP_FINANCE_READ,OU=Groups,DC=corp,DC=local"
        return 9

    async def _fake_build_identity_source_capsule_context(identity_source_id: int) -> dict:
        assert identity_source_id == 9
        return {
            "identity_source_id": 9,
            "host": "dc01.corp.local",
            "bind_dn": "CN=svc,DC=corp,DC=local",
            "secret_ref": "sm://ad/writer",
            "protocol": "ldaps",
            "port": 636,
            "base_dn": "DC=corp,DC=local",
            "verify_tls": False,
            "timeout": 5,
        }

    async def _fake_create_and_publish_job(*, payload: dict, dal_post_fn=None, actor=None) -> dict:
        created_calls.append(payload)
        return {"job_id": 2203}

    monkeypatch.setattr(api, "_resolve_identity_source_id_for_group_operation", _fake_resolve_identity_source_id_for_group_operation)
    monkeypatch.setattr(api, "build_identity_source_capsule_context", _fake_build_identity_source_capsule_context)
    monkeypatch.setattr(api, "create_and_publish_job", _fake_create_and_publish_job)

    response = SimpleNamespace(status_code=None)
    payload = api.DiscoverGroupUsersRecursiveIn(
        identity_source_id=9,
        root_group_dn="CN=GRP_FINANCE_READ,OU=Groups,DC=corp,DC=local",
        max_depth=12,
    )
    out = asyncio.run(api.discover_ad_group_users_recursive(payload=payload, request=None, response=response))

    body = out["data"]
    assert body["ok"] is True
    assert body["job_id"] == 2203
    assert body["status"] == "QUEUED"
    assert body["identity_source_id"] == 9
    assert response.status_code == 202
    assert created_calls[0]["job_type"] == "GROUP_USERS_DISCOVERY"
    assert created_calls[0]["action"] == "discover_group_users_recursive"
    assert created_calls[0]["payload_json"]["payload"]["root_group_dn"] == "CN=GRP_FINANCE_READ,OU=Groups,DC=corp,DC=local"
    assert created_calls[0]["payload_json"]["payload"]["max_depth"] == 12


def test_get_storage_root_access_profile_readiness_ready(monkeypatch) -> None:
    async def _fake_dal_get(path: str, timeout: int = 5):
        _ = timeout
        assert path == "/api/internal/provisioning/storage-roots/10/context"
        return {
            "storage_root_id": 10,
            "zone_id": 3,
            "identity_source_id": 9,
            "identity_source_kind": "AD",
            "write_enabled": 1,
            "secret_ref": "sm://ad/writer",
            "effective_group_ou_dn": "OU=Groups,DC=corp,DC=local",
        }

    monkeypatch.setattr(api, "dal_get", _fake_dal_get)

    out = asyncio.run(api.get_storage_root_access_profile_readiness(10))
    body = out["data"]
    assert body["storage_root_id"] == 10
    assert body["ready"] is True
    assert body["write_enabled"] is True
    assert body["has_secret_ref"] is True
    assert body["effective_group_ou_dn"] == "OU=Groups,DC=corp,DC=local"
    assert body["missing_requirements"] == []


def test_get_storage_root_access_profile_readiness_missing_requirements(monkeypatch) -> None:
    async def _fake_dal_get(path: str, timeout: int = 5):
        _ = timeout
        assert path == "/api/internal/provisioning/storage-roots/11/context"
        return {
            "storage_root_id": 11,
            "zone_id": 4,
            "identity_source_id": 12,
            "identity_source_kind": "OIDC",
            "write_enabled": 0,
            "secret_ref": None,
            "effective_group_ou_dn": None,
        }

    monkeypatch.setattr(api, "dal_get", _fake_dal_get)

    out = asyncio.run(api.get_storage_root_access_profile_readiness(11))
    body = out["data"]
    assert body["ready"] is False
    codes = {str(row.get("code")) for row in (body.get("missing_requirements") or [])}
    assert "IDENTITY_SOURCE_NOT_AD" in codes
    assert "WRITE_NOT_ENABLED" in codes
    assert "SECRET_REF_MISSING" in codes
    assert "EFFECTIVE_GROUP_OU_DN_MISSING" in codes


def test_create_access_profile_returns_structured_not_ready_error(monkeypatch) -> None:
    async def _fake_dal_get(path: str, timeout: int = 5):
        _ = timeout
        assert path == "/api/internal/provisioning/storage-roots/99/context"
        return {
            "storage_root_id": 99,
            "zone_id": 8,
            "identity_source_id": 21,
            "identity_source_kind": "AD",
            "write_enabled": 0,
            "secret_ref": None,
            "effective_group_ou_dn": "OU=Groups,DC=corp,DC=local",
        }

    monkeypatch.setattr(api, "dal_get", _fake_dal_get)

    payload = api.AccessProfileCreateIn(access_level="READ", rights=[])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(api.create_storage_root_access_profile(99, payload))

    assert exc.value.status_code == 422
    detail = exc.value.detail if isinstance(exc.value.detail, dict) else {}
    assert detail.get("code") == "ACCESS_PROFILE_ATTACH_NOT_READY"
    details = detail.get("details") if isinstance(detail.get("details"), dict) else {}
    assert details.get("storage_root_id") == 99
    assert details.get("ready") is False


def test_create_access_profile_rejects_invalid_effective_group_ou_dn(monkeypatch) -> None:
    async def _fake_dal_get(path: str, timeout: int = 5):
        _ = timeout
        assert path == "/api/internal/provisioning/storage-roots/99/context"
        return {
            "storage_root_id": 99,
            "zone_id": 8,
            "identity_source_id": 21,
            "identity_source_kind": "AD",
            "write_enabled": 1,
            "secret_ref": "sm://ad/writer",
            "effective_group_ou_dn": "OU=Groups,INVALID",
        }

    monkeypatch.setattr(api, "dal_get", _fake_dal_get)

    payload = api.AccessProfileCreateIn(access_level="READ", rights=[])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(api.create_storage_root_access_profile(99, payload))

    assert exc.value.status_code == 422
    detail = exc.value.detail if isinstance(exc.value.detail, dict) else {}
    assert detail.get("code") == "INVALID_TARGET_OU_DN"
    assert detail.get("target_ou_dn") == "OU=Groups,INVALID"


def test_watchdog_once_republishes_then_fails_when_limit_reached(monkeypatch) -> None:
    post_calls: list[tuple[str, dict]] = []
    publish_calls: list[tuple[str, int]] = []

    async def _fake_dal_get(path: str, timeout: int = 5):
        _ = timeout
        assert "/api/internal/provisioning/jobs?" in path
        return [
            {
                "id": 101,
                "status": "QUEUED",
                "job_type": "AD_GROUP_ENSURE",
                "metrics_json": {"watchdog_republish_count": 0},
                "action": "ensure_ad_group",
            },
            {
                "id": 102,
                "status": "QUEUED",
                "job_type": "AD_GROUP_ENSURE",
                "metrics_json": {"watchdog_republish_count": 1},
                "action": "ensure_ad_group",
            },
        ]

    async def _fake_dal_post(path: str, payload: dict, timeout: int = 5):
        _ = timeout
        post_calls.append((path, dict(payload)))
        return {"ok": True}

    def _fake_publish(job_type: str | None, job_id: int) -> None:
        publish_calls.append((str(job_type or ""), int(job_id)))

    monkeypatch.setattr(api, "dal_get", _fake_dal_get)
    monkeypatch.setattr(api, "dal_post", _fake_dal_post)
    monkeypatch.setattr(api, "publish_job", _fake_publish)

    out = asyncio.run(
        api.run_queued_jobs_watchdog_once(
            queued_timeout_seconds=300,
            max_republish_count=1,
            limit=200,
            correlation_id="corr_watchdog_once",
        )
    )

    assert out["ok"] is True
    assert out["inspected_count"] == 2
    assert out["republished_count"] == 1
    assert out["republished_job_ids"] == [101]
    assert out["failed_count"] == 1
    assert out["failed_job_ids"] == [102]
    assert publish_calls == [("AD_GROUP_ENSURE", 101)]
    assert post_calls[0][0] == "/api/internal/provisioning/jobs/101/watchdog-republish-mark"
    assert post_calls[1][0] == "/api/internal/provisioning/jobs/102/fail"
    assert post_calls[1][1]["error_code"] == "JOB_QUEUED_TIMEOUT"


def test_list_admin_jobs_proxies_query_to_dal(monkeypatch) -> None:
    captured_paths: list[str] = []

    async def _fake_dal_get(path: str, timeout: int = 5):
        _ = timeout
        captured_paths.append(path)
        return [{"id": 301, "status": "QUEUED"}]

    monkeypatch.setattr(api, "dal_get", _fake_dal_get)

    req = SimpleNamespace(query_params={"status": "QUEUED", "limit": "50"})
    out = asyncio.run(api.list_admin_jobs(req))

    assert out["meta"]["count"] == 1
    assert out["data"][0]["id"] == 301
    assert captured_paths[0].startswith("/api/internal/provisioning/jobs?")
    assert "status=QUEUED" in captured_paths[0]
    assert "limit=50" in captured_paths[0]


def test_cancel_admin_job_uses_request_context_defaults(monkeypatch) -> None:
    post_calls: list[tuple[str, dict]] = []

    async def _fake_dal_post(path: str, payload: dict, timeout: int = 5):
        _ = timeout
        post_calls.append((path, dict(payload)))
        return {"id": 401, "status": "CANCELLED"}

    monkeypatch.setattr(api, "dal_post", _fake_dal_post)

    req = SimpleNamespace(
        headers={"x-request-id": "rid-cancel-1", "x-identity-id": "77"},
        json=lambda: None,
    )

    async def _json():
        return {"reason": "Stop now"}

    req.json = _json
    out = asyncio.run(api.cancel_admin_job(401, req))

    assert out["data"]["status"] == "CANCELLED"
    assert post_calls[0][0] == "/api/internal/provisioning/jobs/401/cancel"
    assert post_calls[0][1]["correlation_id"] == "rid-cancel-1"
    assert post_calls[0][1]["requested_by"] == "77"
    assert post_calls[0][1]["reason"] == "Stop now"
    assert post_calls[0][1]["source"] == "ui"


def test_run_admin_jobs_watchdog_calls_once_with_payload(monkeypatch) -> None:
    captured_args: dict = {}

    async def _fake_watchdog_once(**kwargs):
        captured_args.update(kwargs)
        return {"ok": True, "republished_count": 2, "failed_count": 1}

    monkeypatch.setattr(api, "run_queued_jobs_watchdog_once", _fake_watchdog_once)

    req = SimpleNamespace(headers={"x-request-id": "rid-watchdog-2"})

    async def _json():
        return {
            "queued_timeout_seconds": 120,
            "max_republish_count": 3,
            "limit": 25,
        }

    req.json = _json
    out = asyncio.run(api.run_admin_jobs_watchdog(req))

    assert out["data"]["ok"] is True
    assert captured_args["queued_timeout_seconds"] == 120
    assert captured_args["max_republish_count"] == 3
    assert captured_args["limit"] == 25
    assert captured_args["correlation_id"] == "rid-watchdog-2"
