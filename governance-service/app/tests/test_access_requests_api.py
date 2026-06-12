from __future__ import annotations

import asyncio

from fastapi import HTTPException

from app.api import access_requests as api


class _Req:
    def __init__(self, payload: dict, *, request_id: str = "req_test_123", headers: dict | None = None) -> None:
        self._payload = payload
        self.headers = {"x-request-id": request_id, "x-identity-id": "7", "x-roles": "user", **(headers or {})}

    async def json(self):
        return dict(self._payload)


def test_bulk_decision_non_approve_proxies_to_dal(monkeypatch) -> None:
    calls: list[tuple[str, dict, int, str | None, int]] = []

    async def _fake_dal_post(
        path: str,
        payload: dict,
        timeout: int = 5,
        request_id: str | None = None,
        retries: int = 0,
        extra_headers: dict | None = None,
    ):
        calls.append((path, dict(payload), int(timeout), request_id, int(retries), dict(extra_headers or {})))
        return {
            "data": {
                "ok": True,
                "decision": "reject",
                "requested_ids": [1],
                "updated_ids": [1],
                "failed_ids": [],
                "failed_reasons": {},
                "updated_count": 1,
                "executions_started": 0,
            }
        }

    monkeypatch.setattr(api, "dal_post", _fake_dal_post)

    out = asyncio.run(api.bulk_decision(_Req({"ids": [1], "decision": "reject"})))

    assert out["data"]["ok"] is True
    assert out["data"]["decision"] == "reject"
    assert calls[0][0] == "/api/access-requests/bulk"
    assert calls[0][1] == {"ids": [1], "decision": "reject"}
    assert calls[0][2] == 30
    assert calls[0][3] == "req_test_123"
    assert calls[0][4] == 2
    assert calls[0][5]["x-identity-id"] == "7"


def test_bulk_decision_approve_orchestrates_and_marks_approved(monkeypatch) -> None:
    post_calls: list[tuple[str, dict]] = []

    async def _fake_dal_get(
        path: str,
        timeout: int = 5,
        request_id: str | None = None,
        retries: int = 0,
        extra_headers: dict | None = None,
    ):
        _ = timeout, request_id, retries
        assert path == "/api/internal/access-requests/101/provisioning-plan"
        assert dict(extra_headers or {}).get("x-identity-id") == "7"
        return {
            "access_request_id": 101,
            "principal": {"dn": "CN=Jane,OU=Users,DC=example,DC=com", "username": "jane"},
            "items": [
                {
                    "id": 201,
                    "target_type": "storage_root",
                    "target_id": 77,
                    "permission": "read",
                    "access_level_code": "READ",
                    "storage_root_access_profile_id": 501,
                    "group_ref": "B2S_ROOT_77_READ",
                    "profile_status": "QUEUED",
                    "group_external_id": None,
                    "identity_source_id": 9,
                    "error": None,
                }
            ],
        }

    async def _fake_dal_post(
        path: str,
        payload: dict,
        timeout: int = 5,
        request_id: str | None = None,
        retries: int = 0,
        extra_headers: dict | None = None,
    ):
        _ = timeout, request_id, retries, extra_headers
        post_calls.append((path, dict(payload)))
        if path == "/api/internal/access-requests/item-executions":
            return {"ok": True}
        if path == "/api/access-requests/bulk":
            return {"data": {"ok": True}}
        raise AssertionError(path)

    async def _fake_ensure_group(payload, request=None, response=None):
        _ = request, response
        assert payload.group_name == "B2S_ROOT_77_READ"
        return {"data": {"ok": True, "job_id": 7001, "status": "QUEUED"}}

    async def _fake_ensure_member(payload, request=None, response=None):
        _ = request, response
        assert payload.group_ref == "B2S_ROOT_77_READ"
        assert payload.principal_username == "jane"
        return {"data": {"ok": True, "job_id": 7002, "status": "QUEUED"}}

    async def _fake_submit_probe_run(payload: dict):
        assert payload["kind"] == "acl"
        return {"job_id": "8001", "status": "queued", "poll_url": "/api/probes/jobs/8001"}

    async def _fake_fetch_probe_job(job_id: int | str):
        assert str(job_id) == "8001"
        return {"job_id": "8001", "status": "succeeded", "result": {"message": "ACL applied"}}

    monkeypatch.setattr(api, "dal_get", _fake_dal_get)
    monkeypatch.setattr(api, "dal_post", _fake_dal_post)
    monkeypatch.setattr(api, "ensure_ad_group_via_name", _fake_ensure_group)
    monkeypatch.setattr(api, "ensure_ad_group_member", _fake_ensure_member)
    monkeypatch.setattr(api, "submit_probe_run", _fake_submit_probe_run)
    monkeypatch.setattr(api, "fetch_probe_job", _fake_fetch_probe_job)

    out = asyncio.run(
        api.bulk_decision(_Req({"ids": [101], "decision": "approve", "decision_comment": "Validated by guardian"}))
    )

    assert out["data"]["ok"] is True
    assert out["data"]["updated_ids"] == [101]
    assert out["data"]["failed_ids"] == []
    assert out["data"]["executions_started"] == 1
    assert post_calls[0][0] == "/api/internal/access-requests/item-executions"
    assert str(post_calls[0][1].get("status") or "").upper() == "DONE"
    req_payload = dict(post_calls[0][1].get("requested_payload_json") or {})
    assert str(req_payload.get("correlation_id") or "").startswith("ar_101_201_")
    assert post_calls[1] == (
        "/api/access-requests/bulk",
        {"ids": [101], "decision": "approve", "decision_comment": "Validated by guardian"},
    )


def test_bulk_decision_approve_records_failure_and_skips_mark_approved(monkeypatch) -> None:
    post_calls: list[tuple[str, dict]] = []

    async def _fake_dal_get(
        path: str,
        timeout: int = 5,
        request_id: str | None = None,
        retries: int = 0,
        extra_headers: dict | None = None,
    ):
        _ = timeout, request_id, retries, extra_headers
        assert path == "/api/internal/access-requests/202/provisioning-plan"
        return {
            "access_request_id": 202,
            "principal": {"dn": "CN=Jane,OU=Users,DC=example,DC=com", "username": "jane"},
            "items": [
                {
                    "id": 301,
                    "target_type": "storage_root",
                    "target_id": 77,
                    "permission": "read",
                    "access_level_code": "READ",
                    "storage_root_access_profile_id": 501,
                    "group_ref": "",
                    "profile_status": "QUEUED",
                    "group_external_id": None,
                    "identity_source_id": 9,
                    "error": "Group reference is missing",
                }
            ],
        }

    async def _fake_dal_post(
        path: str,
        payload: dict,
        timeout: int = 5,
        request_id: str | None = None,
        retries: int = 0,
        extra_headers: dict | None = None,
    ):
        _ = timeout, request_id, retries, extra_headers
        post_calls.append((path, dict(payload)))
        if path == "/api/internal/access-requests/item-executions":
            return {"ok": True}
        raise AssertionError(path)

    monkeypatch.setattr(api, "dal_get", _fake_dal_get)
    monkeypatch.setattr(api, "dal_post", _fake_dal_post)

    out = asyncio.run(api.bulk_decision(_Req({"ids": [202], "decision": "approve"})))

    assert out["data"]["ok"] is False
    assert out["data"]["updated_ids"] == []
    assert out["data"]["failed_ids"] == [202]
    assert post_calls == [
        (
            "/api/internal/access-requests/item-executions",
            {
                "access_request_id": 202,
                "access_request_item_id": 301,
                "status": "FAILED",
                "requested_payload_json": {
                    "correlation_id": "ar_202_301_plan",
                    "target_type": "storage_root",
                    "target_id": 77,
                    "permission": "read",
                },
                "result_json": None,
                "error_message": "Group reference is missing",
            },
        )
    ]


def test_bulk_decision_approve_uses_implicit_governed_group_without_profile_binding(monkeypatch) -> None:
    post_calls: list[tuple[str, dict]] = []
    get_calls: list[str] = []

    async def _fake_dal_get(
        path: str,
        timeout: int = 5,
        request_id: str | None = None,
        retries: int = 0,
        extra_headers: dict | None = None,
    ):
        _ = timeout, request_id, retries, extra_headers
        get_calls.append(path)
        assert path == "/api/internal/access-requests/303/provisioning-plan"
        return {
            "access_request_id": 303,
            "principal": {"dn": "CN=Jane,OU=Users,DC=example,DC=com", "username": "jane"},
            "items": [
                {
                    "id": 401,
                    "target_type": "storage_root",
                    "target_id": 77,
                    "permission": "read",
                    "access_level_code": "READ",
                    "storage_root_access_profile_id": None,
                    "group_ref": "B2S_RH_RX",
                    "profile_status": None,
                    "group_external_id": None,
                    "identity_source_id": 9,
                    "error": None,
                }
            ],
        }

    async def _fake_dal_post(
        path: str,
        payload: dict,
        timeout: int = 5,
        request_id: str | None = None,
        retries: int = 0,
        extra_headers: dict | None = None,
    ):
        _ = timeout, request_id, retries, extra_headers
        post_calls.append((path, dict(payload)))
        if path == "/api/internal/access-requests/item-executions":
            return {"ok": True}
        if path == "/api/access-requests/bulk":
            return {"data": {"ok": True}}
        raise AssertionError(path)

    async def _fake_ensure_group(payload, request=None, response=None):
        _ = request, response
        assert payload.group_name == "B2S_RH_RX"
        return {"data": {"ok": True, "job_id": 7001, "status": "QUEUED"}}

    async def _fake_ensure_member(payload, request=None, response=None):
        _ = request, response
        assert payload.group_ref == "B2S_RH_RX"
        assert payload.principal_username == "jane"
        return {"data": {"ok": True, "job_id": 7002, "status": "QUEUED"}}

    async def _fake_submit_probe_run(payload: dict):
        assert payload["kind"] == "acl"
        return {"job_id": "8001", "status": "queued", "poll_url": "/api/probes/jobs/8001"}

    async def _fake_fetch_probe_job(job_id: int | str):
        assert str(job_id) == "8001"
        return {"job_id": "8001", "status": "succeeded", "result": {"message": "ACL applied"}}

    monkeypatch.setattr(api, "dal_get", _fake_dal_get)
    monkeypatch.setattr(api, "dal_post", _fake_dal_post)
    monkeypatch.setattr(api, "ensure_ad_group_via_name", _fake_ensure_group)
    monkeypatch.setattr(api, "ensure_ad_group_member", _fake_ensure_member)
    monkeypatch.setattr(api, "submit_probe_run", _fake_submit_probe_run)
    monkeypatch.setattr(api, "fetch_probe_job", _fake_fetch_probe_job)

    out = asyncio.run(api.bulk_decision(_Req({"ids": [303], "decision": "approve"})))

    assert out["data"]["ok"] is True
    assert out["data"]["updated_ids"] == [303]
    assert out["data"]["failed_ids"] == []
    assert get_calls == ["/api/internal/access-requests/303/provisioning-plan"]


def test_bulk_decision_non_approve_preserves_dal_http_exception(monkeypatch) -> None:
    async def _fake_dal_post(
        path: str,
        payload: dict,
        timeout: int = 5,
        request_id: str | None = None,
        retries: int = 0,
        extra_headers: dict | None = None,
    ):
        _ = path, payload, timeout, request_id, retries, extra_headers
        raise HTTPException(status_code=502, detail={"error_code": "GOVERNANCE_DAL_FAILURE"})

    monkeypatch.setattr(api, "dal_post", _fake_dal_post)

    try:
        asyncio.run(api.bulk_decision(_Req({"ids": [1], "decision": "reject"}, request_id="req_test_502")))
        raised = False
    except HTTPException as exc:
        raised = True
        assert exc.status_code == 502
        assert isinstance(exc.detail, dict)
        assert exc.detail.get("error_code") == "GOVERNANCE_DAL_FAILURE"

    assert raised is True


def test_bulk_decision_rejects_missing_reviewer_identity() -> None:
    try:
        asyncio.run(api.bulk_decision(_Req({"ids": [1], "decision": "reject"}, headers={"x-identity-id": ""})))
        raised = False
    except HTTPException as exc:
        raised = True
        assert exc.status_code == 403
        assert isinstance(exc.detail, dict)
        assert exc.detail.get("error_code") == "REVIEWER_CONTEXT_REQUIRED"

    assert raised is True
