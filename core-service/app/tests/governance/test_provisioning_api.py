from __future__ import annotations

import asyncio
import pytest
from types import SimpleNamespace

from fastapi import HTTPException

from app.api.governance import provisioning as api
from app.schemas.provisioning import EnsureAdGroupContextIn
from app.tests.governance.route_fakes import fake_routes


def test_ensure_ad_group_via_name_uses_payload_secret_ref_and_returns_202(monkeypatch) -> None:
    post_calls: list[tuple[str, dict]] = []
    queue_calls = {"count": 0}
    log_calls: list[str] = []

    async def _fake_internal_get(path: str):
        raise AssertionError(path)

    async def _fake_internal_post(path: str, payload: dict):
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

    fake_routes(monkeypatch, api, get=_fake_internal_get)
    fake_routes(monkeypatch, api, post=_fake_internal_post)
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


def test_ensure_ad_group_via_name_reuses_active_job_of_access_group(monkeypatch) -> None:
    async def _fake_internal_get(path: str):
        if path.startswith("/api/internal/provisioning/jobs?") and "storage_root_access_profile_id=77" in path:
            assert "active_only=true" in path and "job_type=AD_GROUP_ENSURE" in path
            return [{"id": 701, "status": "RUNNING", "correlation_id": "corr-existing"}]
        raise AssertionError(path)

    async def _fake_internal_post(path: str, payload: dict):
        raise AssertionError(path)

    class _FakeActor:
        @staticmethod
        def send(job_id: int):
            raise AssertionError(job_id)

    fake_routes(monkeypatch, api, get=_fake_internal_get)
    fake_routes(monkeypatch, api, post=_fake_internal_post)
    monkeypatch.setattr(api, "run_provisioning_job", _FakeActor())

    payload = api.EnsureAdGroupIn(
        group_name="B2S_FINANCE_READ",
        target_ou_dn="OU=Groups,DC=corp,DC=local",
        secret_ref="sm://ad/writer",
        context=EnsureAdGroupContextIn(storage_root_access_profile_id=77),
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

    async def _fake_internal_get(path: str):
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

    async def _fake_internal_post(path: str, payload: dict):
        post_calls.append((path, payload))
        if path == "/api/internal/provisioning/jobs":
            return {"created": True, "data": {"id": 9902}}
        raise AssertionError(path)

    class _FakeActor:
        @staticmethod
        def send(job_id: int):
            queue_calls["count"] += 1
            assert job_id == 9902

    fake_routes(monkeypatch, api, get=_fake_internal_get)
    fake_routes(monkeypatch, api, post=_fake_internal_post)
    monkeypatch.setattr(api, "run_provisioning_job", _FakeActor())
    monkeypatch.setattr(api, "log_event", lambda **kwargs: None)

    payload = api.EnsureAdGroupIn(
        group_name="B2S_FINANCE_READ",
        context=EnsureAdGroupContextIn(storage_root_id=8010),
    )
    out = asyncio.run(api.ensure_ad_group_via_name(payload=payload, request=None, response=None))

    assert out["data"]["ok"] is True
    assert post_calls[0][0] == "/api/internal/provisioning/jobs"
    assert post_calls[0][1]["payload_json"]["payload"]["target_ou_dn"] == "OU=ZoneGroups,DC=corp,DC=local"
    assert queue_calls["count"] == 1


def test_ensure_ad_group_via_name_falls_back_to_identity_default_ou(monkeypatch) -> None:
    post_calls: list[tuple[str, dict]] = []

    async def _fake_internal_get(path: str):
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

    async def _fake_internal_post(path: str, payload: dict):
        post_calls.append((path, payload))
        if path == "/api/internal/provisioning/jobs":
            return {"created": True, "data": {"id": 9903}}
        raise AssertionError(path)

    fake_routes(monkeypatch, api, get=_fake_internal_get)
    fake_routes(monkeypatch, api, post=_fake_internal_post)
    monkeypatch.setattr(api, "run_provisioning_job", type("_A", (), {"send": staticmethod(lambda _jid: None)})())
    monkeypatch.setattr(api, "log_event", lambda **kwargs: None)

    payload = api.EnsureAdGroupIn(
        group_name="B2S_FINANCE_READ",
        context=EnsureAdGroupContextIn(storage_root_id=8010),
    )
    out = asyncio.run(api.ensure_ad_group_via_name(payload=payload, request=None, response=None))

    assert out["data"]["ok"] is True
    assert post_calls[0][1]["payload_json"]["payload"]["target_ou_dn"] == "OU=DefaultGroups,DC=corp,DC=local"


def test_ensure_ad_group_via_name_rejects_invalid_target_ou_dn(monkeypatch) -> None:
    async def _fake_internal_get(path: str):
        raise AssertionError(path)

    async def _fake_internal_post(path: str, payload: dict):
        raise AssertionError(path)

    fake_routes(monkeypatch, api, get=_fake_internal_get)
    fake_routes(monkeypatch, api, post=_fake_internal_post)

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

    async def _fake_internal_get(path: str):
        raise AssertionError(path)

    async def _fake_internal_post(path: str, payload: dict):
        post_calls.append((path, payload))
        if path == "/api/internal/provisioning/jobs":
            return {"created": True, "data": {"id": 9904}}
        raise AssertionError(path)

    class _FakeActor:
        @staticmethod
        def send(job_id: int):
            queue_calls["count"] += 1
            assert job_id == 9904

    fake_routes(monkeypatch, api, get=_fake_internal_get)
    fake_routes(monkeypatch, api, post=_fake_internal_post)
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

    async def _fake_create_and_publish_job(*, payload: dict, internal_post_fn=None, actor=None) -> dict:
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

    async def _fake_create_and_publish_job(*, payload: dict, internal_post_fn=None, actor=None) -> dict:
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


def test_watchdog_once_republishes_then_fails_when_limit_reached(monkeypatch) -> None:
    post_calls: list[tuple[str, dict]] = []
    publish_calls: list[tuple[str, int]] = []

    async def _fake_internal_get(path: str):
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

    async def _fake_internal_post(path: str, payload: dict):
        post_calls.append((path, dict(payload)))
        return {"ok": True}

    def _fake_publish(job_type: str | None, job_id: int) -> None:
        publish_calls.append((str(job_type or ""), int(job_id)))

    fake_routes(monkeypatch, api, get=_fake_internal_get)
    fake_routes(monkeypatch, api, post=_fake_internal_post)
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


def test_list_admin_jobs_proxies_query_to_core(monkeypatch) -> None:
    captured_paths: list[str] = []

    async def _fake_internal_get(path: str):
        captured_paths.append(path)
        return [{"id": 301, "status": "QUEUED"}]

    fake_routes(monkeypatch, api, get=_fake_internal_get)

    out = asyncio.run(api.list_admin_jobs(status_filter="QUEUED", limit=50))

    assert out["meta"]["count"] == 1
    assert out["data"][0]["id"] == 301
    assert captured_paths[0].startswith("/api/internal/provisioning/jobs?")
    assert "status=QUEUED" in captured_paths[0]
    assert "limit=50" in captured_paths[0]


def test_cancel_admin_job_uses_request_context_defaults(monkeypatch) -> None:
    post_calls: list[tuple[str, dict]] = []

    async def _fake_internal_post(path: str, payload: dict):
        post_calls.append((path, dict(payload)))
        return {"id": 401, "status": "CANCELLED"}

    fake_routes(monkeypatch, api, post=_fake_internal_post)

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

