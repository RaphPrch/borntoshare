from __future__ import annotations

import asyncio

import pytest

from fastapi import HTTPException

from app.api.governance import access_requests as api
from app.tests.governance.route_fakes import fake_routes


class _Req:
    def __init__(self, payload: dict, *, request_id: str = "req_test_123", headers: dict | None = None) -> None:
        self._payload = payload
        self.headers = {"x-request-id": request_id, "x-identity-id": "7", "x-roles": "user", **(headers or {})}

    async def json(self):
        return dict(self._payload)


@pytest.fixture(autouse=True)
def _no_activity_log(monkeypatch):
    """The provisioning log goes to the logging database: tests that check it capture it."""
    monkeypatch.setattr(api, "log_event", lambda **kw: None)


def _capture_journal(monkeypatch) -> list[tuple[str, dict]]:
    entries: list[tuple[str, dict]] = []
    monkeypatch.setattr(api, "log_event", lambda **kw: entries.append((kw["action"], kw)))
    return entries


def _fake_grant(monkeypatch, *, job: dict | None = None, still_running: bool = False) -> list[dict]:
    """Grant job queued then finished with `job` (default: group created + member added)."""
    calls: list[dict] = []

    async def _queue(**kw):
        calls.append({k: kw[k] for k in (
            "storage_root_id", "access_profile_id", "group_name", "group_external_id", "adopt_group_dn", "principal_username",
        )})
        return {"job_id": 7001, "identity_source_id": 9, "target_ou_dn": "OU=Groups,DC=example,DC=com", "zone_id": 3}

    async def _wait(job_id, *, timeout_sec=60, interval_sec=1.0):
        assert job_id == 7001
        if still_running:
            return None
        return job or {
            "id": 7001,
            "status": "SUCCEEDED",
            "result_json": {"success": True, "details": {
                "group_name": calls[-1]["group_name"],
                "group_dn": f"CN={calls[-1]['group_name']},OU=Groups,DC=example,DC=com",
                "group_outcome": "created",
                "member_outcome": "added",
                "principal_dn": "CN=Jane,OU=Users,DC=example,DC=com",
            }},
        }

    monkeypatch.setattr(api, "queue_ad_access_grant", _queue)
    monkeypatch.setattr(api, "wait_provisioning_job", _wait)
    return calls


def _single_item_plan(req_id: int) -> dict:
    return {
        "access_request_id": req_id,
        "principal": {"dn": "CN=Jane,OU=Users,DC=example,DC=com", "username": "jane"},
        "items": [{
            "id": 201,
            "target_type": "storage_root",
            "target_id": 77,
            "permission": "write",
            "access_level_code": "WRITE",
            "group_ref": "B2S_ROOT_77_RW",
            "identity_source_id": 9,
            "error": None,
        }],
    }


def _approval_posts(profile: dict, calls: list[tuple[str, dict]]):
    async def _post(path: str, payload: dict):
        calls.append((path, dict(payload)))
        if path == "/api/internal/provisioning/storage-root-access-profiles":
            return {"created": False, "data": profile}
        if path == "/api/internal/access-requests/item-executions":
            return {"ok": True}
        if path == "/api/access-requests/bulk":
            return {"data": {"ok": True}}
        raise AssertionError(path)

    return _post


def test_bulk_decision_approve_group_name_conflict_offers_adoption(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    async def _get(path: str):
        return _single_item_plan(404)

    fake_routes(monkeypatch, api, get=_get)
    fake_routes(monkeypatch, api, post=_approval_posts({"id": 56, "group_name": "B2S_ROOT_77_RW", "status": "PENDING"}, calls))
    _fake_grant(monkeypatch, job={
        "id": 7001,
        "status": "FAILED",
        "error_code": "AD_GROUP_NAME_CONFLICT",
        "error_message": "A group with this name already exists outside the organizational unit of the zone",
        "result_json": {"success": False, "details": {"existing_dn": "CN=B2S_ROOT_77_RW,OU=Legacy,DC=example,DC=com"}},
    })
    journal = _capture_journal(monkeypatch)

    out = asyncio.run(api.bulk_decision(_Req({"ids": [404], "decision": "approve"})))

    assert out["data"]["failed_ids"] == [404]
    detail = out["data"]["failed_details"][404]
    assert detail["code"] == "AD_GROUP_NAME_CONFLICT"
    assert detail["existing_dn"] == "CN=B2S_ROOT_77_RW,OU=Legacy,DC=example,DC=com"
    assert detail["access_profile_id"] == 56
    assert detail["job_id"] == 7001
    # Not approved: the request stays pending
    assert "/api/access-requests/bulk" not in [path for path, _ in calls]
    actions = [action for action, _ in journal]
    assert actions[-2:] == ["access_request_step_failed", "access_request_approval_failed"]
    assert journal[-2][1]["metadata_json"]["code"] == "AD_GROUP_NAME_CONFLICT"


def test_bulk_decision_approve_adopts_the_group_chosen_by_an_admin(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    async def _get(path: str):
        return _single_item_plan(405)

    async def _probe(payload: dict):
        return {"job_id": "8002", "status": "queued"}

    async def _probe_job(job_id):
        return {"job_id": "8002", "status": "succeeded"}

    fake_routes(monkeypatch, api, get=_get)
    adopting = {"id": 56, "group_name": "B2S_ROOT_77_RW", "status": "ADOPTING", "group_external_id": "CN=B2S_ROOT_77_RW,OU=Legacy,DC=example,DC=com"}
    fake_routes(monkeypatch, api, post=_approval_posts(adopting, calls))
    grants = _fake_grant(monkeypatch)
    _capture_journal(monkeypatch)
    monkeypatch.setattr(api, "submit_probe_run", _probe)
    monkeypatch.setattr(api, "fetch_probe_job", _probe_job)

    out = asyncio.run(api.bulk_decision(_Req({"ids": [405], "decision": "approve"})))

    assert out["data"]["updated_ids"] == [405]
    assert grants[0]["adopt_group_dn"] == "CN=B2S_ROOT_77_RW,OU=Legacy,DC=example,DC=com"
    assert grants[0]["group_external_id"] is None


def test_bulk_decision_approve_reuses_the_known_group(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    async def _get(path: str):
        return _single_item_plan(406)

    async def _probe(payload: dict):
        return {"job_id": "8003", "status": "queued"}

    async def _probe_job(job_id):
        return {"job_id": "8003", "status": "succeeded"}

    fake_routes(monkeypatch, api, get=_get)
    known = {"id": 56, "group_name": "B2S_ROOT_77_RW", "status": "SUCCEEDED", "group_external_id": "6f1c0a52-8f8e-4c51-9a3b-1f2d3c4b5a69"}
    fake_routes(monkeypatch, api, post=_approval_posts(known, calls))
    grants = _fake_grant(monkeypatch)
    _capture_journal(monkeypatch)
    monkeypatch.setattr(api, "submit_probe_run", _probe)
    monkeypatch.setattr(api, "fetch_probe_job", _probe_job)

    out = asyncio.run(api.bulk_decision(_Req({"ids": [406], "decision": "approve"})))

    assert out["data"]["updated_ids"] == [406]
    assert grants[0]["group_external_id"] == "6f1c0a52-8f8e-4c51-9a3b-1f2d3c4b5a69"
    assert grants[0]["adopt_group_dn"] is None


def test_bulk_decision_approve_reports_a_job_still_running(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    async def _get(path: str):
        return _single_item_plan(407)

    fake_routes(monkeypatch, api, get=_get)
    fake_routes(monkeypatch, api, post=_approval_posts({"id": 56, "group_name": "B2S_ROOT_77_RW", "status": "PENDING"}, calls))
    _fake_grant(monkeypatch, still_running=True)
    _capture_journal(monkeypatch)

    out = asyncio.run(api.bulk_decision(_Req({"ids": [407], "decision": "approve"})))

    assert out["data"]["failed_ids"] == [407]
    assert out["data"]["failed_details"][407]["code"] == "AD_JOB_STILL_RUNNING"
    assert "/api/access-requests/bulk" not in [path for path, _ in calls]


def test_bulk_decision_non_approve_proxies_to_core(monkeypatch) -> None:
    calls: list[tuple[str, dict, int, str | None, int]] = []

    async def _fake_internal_post(
        path: str,
        payload: dict,
    ):
        calls.append((path, dict(payload)))
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

    fakes = fake_routes(monkeypatch, api, post=_fake_internal_post)

    out = asyncio.run(api.bulk_decision(_Req({"ids": [1], "decision": "reject"})))

    assert out["data"]["ok"] is True
    assert out["data"]["decision"] == "reject"
    assert calls[0][0] == "/api/access-requests/bulk"
    assert calls[0][1] == {"ids": [1], "decision": "reject"}
    # The reviewer's request (and its actor headers) reaches the persisting route
    assert fakes.requests[0].headers["x-identity-id"] == "7"


def test_bulk_decision_approve_orchestrates_and_marks_approved(monkeypatch) -> None:
    post_calls: list[tuple[str, dict]] = []

    async def _fake_internal_get(
        path: str,
    ):
        assert path == "/api/internal/access-requests/101/provisioning-plan"
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

    async def _fake_internal_post(
        path: str,
        payload: dict,
    ):
        post_calls.append((path, dict(payload)))
        if path == "/api/internal/access-requests/item-executions":
            return {"ok": True}
        if path == "/api/internal/provisioning/storage-root-access-profiles":
            # First approval for this level: the access group is recorded before the AD job
            return {"created": True, "data": {"id": 55, "group_name": payload["group_name"], "status": "PENDING"}}
        if path == "/api/access-requests/bulk":
            return {"data": {"ok": True}}
        raise AssertionError(path)

    async def _fake_submit_probe_run(payload: dict):
        assert payload["kind"] == "acl"
        assert payload["target"]["group_name"] == "B2S_ROOT_77_READ"
        return {"job_id": "8001", "status": "queued", "poll_url": "/api/probes/jobs/8001"}

    async def _fake_fetch_probe_job(job_id: int | str):
        assert str(job_id) == "8001"
        return {"job_id": "8001", "status": "succeeded", "result": {"message": "ACL applied"}}

    fake_routes(monkeypatch, api, get=_fake_internal_get)
    fake_routes(monkeypatch, api, post=_fake_internal_post)
    grants = _fake_grant(monkeypatch)
    journal = _capture_journal(monkeypatch)
    monkeypatch.setattr(api, "submit_probe_run", _fake_submit_probe_run)
    monkeypatch.setattr(api, "fetch_probe_job", _fake_fetch_probe_job)

    out = asyncio.run(
        api.bulk_decision(_Req({"ids": [101], "decision": "approve", "decision_comment": "Validated by guardian"}))
    )

    assert out["data"]["ok"] is True
    assert out["data"]["updated_ids"] == [101]
    assert out["data"]["failed_ids"] == []
    assert out["data"]["executions_started"] == 1
    # First approval for READ on this root: the access group is recorded, then the item executes
    assert post_calls[0] == (
        "/api/internal/provisioning/storage-root-access-profiles",
        {"storage_root_id": 77, "access_level_code": "READ", "group_name": "B2S_ROOT_77_READ"},
    )
    assert post_calls[1][0] == "/api/internal/access-requests/item-executions"
    assert str(post_calls[1][1].get("status") or "").upper() == "DONE"
    req_payload = dict(post_calls[1][1].get("requested_payload_json") or {})
    assert str(req_payload.get("correlation_id") or "").startswith("apr_101_")
    assert post_calls[2] == (
        "/api/access-requests/bulk",
        {"ids": [101], "decision": "approve", "decision_comment": "Validated by guardian"},
    )
    # One grant job (group + member) for the access group of the level, created at this first approval
    assert grants == [{
        "storage_root_id": 77,
        "access_profile_id": 55,
        "group_name": "B2S_ROOT_77_READ",
        "group_external_id": None,
        "adopt_group_dn": None,
        "principal_username": "jane",
    }]
    # Every step leaves a log entry on the request
    assert [action for action, _ in journal] == [
        "access_request_approval_started",
        "ad_access_grant_queued",
        "ad_group_created",
        "ad_group_member_added",
        "acl_apply_queued",
        "acl_applied",
        "access_request_applied",
    ]
    assert all(kw["entity_type"] == "access_request" and kw["entity_id"] == 101 for _, kw in journal)
    assert len({kw["correlation_id"] for _, kw in journal}) == 1


def test_bulk_decision_approve_records_failure_and_skips_mark_approved(monkeypatch) -> None:
    post_calls: list[tuple[str, dict]] = []

    async def _fake_internal_get(
        path: str,
    ):
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

    async def _fake_internal_post(
        path: str,
        payload: dict,
    ):
        post_calls.append((path, dict(payload)))
        if path == "/api/internal/access-requests/item-executions":
            return {"ok": True}
        raise AssertionError(path)

    fake_routes(monkeypatch, api, get=_fake_internal_get)
    fake_routes(monkeypatch, api, post=_fake_internal_post)

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

    async def _fake_internal_get(
        path: str,
    ):
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

    async def _fake_internal_post(
        path: str,
        payload: dict,
    ):
        post_calls.append((path, dict(payload)))
        if path == "/api/internal/access-requests/item-executions":
            return {"ok": True}
        if path == "/api/internal/provisioning/storage-root-access-profiles":
            # First approval for this level: the access group is recorded before the AD job
            return {"created": True, "data": {"id": 55, "group_name": payload["group_name"], "status": "PENDING"}}
        if path == "/api/access-requests/bulk":
            return {"data": {"ok": True}}
        raise AssertionError(path)

    async def _fake_submit_probe_run(payload: dict):
        assert payload["kind"] == "acl"
        return {"job_id": "8001", "status": "queued", "poll_url": "/api/probes/jobs/8001"}

    async def _fake_fetch_probe_job(job_id: int | str):
        assert str(job_id) == "8001"
        return {"job_id": "8001", "status": "succeeded", "result": {"message": "ACL applied"}}

    fake_routes(monkeypatch, api, get=_fake_internal_get)
    fake_routes(monkeypatch, api, post=_fake_internal_post)
    grants = _fake_grant(monkeypatch)
    _capture_journal(monkeypatch)
    monkeypatch.setattr(api, "submit_probe_run", _fake_submit_probe_run)
    monkeypatch.setattr(api, "fetch_probe_job", _fake_fetch_probe_job)

    out = asyncio.run(api.bulk_decision(_Req({"ids": [303], "decision": "approve"})))

    assert out["data"]["ok"] is True
    assert out["data"]["updated_ids"] == [303]
    assert out["data"]["failed_ids"] == []
    assert get_calls == ["/api/internal/access-requests/303/provisioning-plan"]
    assert grants[0]["group_name"] == "B2S_RH_RX"


def test_bulk_decision_non_approve_preserves_core_http_exception(monkeypatch) -> None:
    async def _fake_internal_post(
        path: str,
        payload: dict,
    ):
        _ = path, payload
        raise HTTPException(status_code=502, detail={"error_code": "INTERNAL_CALL_FAILURE"})

    fake_routes(monkeypatch, api, post=_fake_internal_post)

    try:
        asyncio.run(api.bulk_decision(_Req({"ids": [1], "decision": "reject"}, request_id="req_test_502")))
        raised = False
    except HTTPException as exc:
        raised = True
        assert exc.status_code == 502
        assert isinstance(exc.detail, dict)
        assert exc.detail.get("error_code") == "INTERNAL_CALL_FAILURE"

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


def _revoke_plan(items: list[dict]) -> dict:
    return {
        "access_request_id": 101,
        "principal": {"dn": "CN=Jane,OU=Users,DC=example,DC=com", "username": "jane"},
        "items": items,
    }


def test_bulk_decision_revoke_removes_memberships_then_persists_in_core(monkeypatch) -> None:
    post_calls: list[tuple[str, dict]] = []
    removed: list[tuple[str, str | None, int | None]] = []

    async def _fake_internal_get(path: str):
        if path.startswith("/api/internal/access-requests/101/other-active"):
            return None  # no other request grants this level
        assert path == "/api/internal/access-requests/101/provisioning-plan"
        return _revoke_plan([
            {
                "id": 201,
                "target_type": "storage_root",
                "target_id": 77,
                "permission": "read",
                "access_level_code": "READ",
                "group_ref": "B2S_ROOT_77_READ",
                "identity_source_id": 9,
                "error": None,
            }
        ])

    async def _fake_internal_post(path: str, payload: dict):
        post_calls.append((path, dict(payload)))
        if path == "/api/internal/access-requests/item-executions":
            return {"ok": True}
        if path == "/api/access-requests/bulk":
            return {"data": {"ok": True, "updated_ids": [101], "failed_ids": []}}
        raise AssertionError(path)

    async def _fake_remove_member(payload, request=None, response=None):
        _ = response
        removed.append((payload.group_ref, payload.principal_username, payload.identity_source_id))
        assert request.headers["x-request-id"].startswith("rev_101_")
        assert request.headers["x-request-id"].endswith("_201_revoke")
        return {"data": {"ok": True, "job_id": 9001, "status": "QUEUED"}}

    async def _fake_wait(job_id, *, timeout_sec=60, interval_sec=1.0):
        assert job_id == 9001
        return {"id": 9001, "status": "SUCCEEDED", "result_json": {"details": {"reason": "removed", "principal_dn": "CN=Jane"}}}

    fake_routes(monkeypatch, api, get=_fake_internal_get)
    fake_routes(monkeypatch, api, post=_fake_internal_post)
    monkeypatch.setattr(api, "remove_ad_group_member", _fake_remove_member)
    monkeypatch.setattr(api, "wait_provisioning_job", _fake_wait)
    journal = _capture_journal(monkeypatch)

    out = asyncio.run(api.bulk_decision(_Req({"ids": [101], "decision": "revoke"})))

    assert out["data"]["ok"] is True
    assert out["data"]["decision"] == "revoke"
    assert out["data"]["updated_ids"] == [101]
    assert out["data"]["failed_ids"] == []
    assert removed == [("B2S_ROOT_77_READ", "jane", 9)]
    assert post_calls[0][0] == "/api/internal/access-requests/item-executions"
    assert post_calls[0][1]["status"] == "DONE"
    assert post_calls[0][1]["requested_payload_json"]["operation"] == "revoke"
    assert post_calls[1] == ("/api/access-requests/bulk", {"ids": [101], "decision": "revoke"})
    # The user leaves the group, the group itself is kept
    assert [action for action, _ in journal] == [
        "access_request_revocation_started",
        "ad_group_member_removal_queued",
        "ad_group_member_removed",
        "access_request_revoked",
    ]
    assert journal[2][1]["metadata_json"]["group_kept"] is True


def test_bulk_decision_revoke_failure_records_item_and_skips_core_persist(monkeypatch) -> None:
    post_calls: list[tuple[str, dict]] = []

    async def _fake_internal_get(path: str):
        return _revoke_plan([
            {
                "id": 201,
                "target_type": "storage_root",
                "target_id": 77,
                "permission": "read",
                "access_level_code": "READ",
                "group_ref": None,
                "identity_source_id": None,
                "error": "No governed group bound",
                "error_detail": {"message": "No governed group bound to READ"},
            }
        ])

    async def _fake_internal_post(path: str, payload: dict):
        post_calls.append((path, dict(payload)))
        return {"ok": True}

    async def _fail_remove_member(payload, request=None, response=None):
        raise AssertionError("must not remove a membership for an unresolved item")

    fake_routes(monkeypatch, api, get=_fake_internal_get)
    fake_routes(monkeypatch, api, post=_fake_internal_post)
    monkeypatch.setattr(api, "remove_ad_group_member", _fail_remove_member)

    out = asyncio.run(api.bulk_decision(_Req({"ids": [101], "decision": "revoke"})))

    assert out["data"]["ok"] is False
    assert out["data"]["updated_ids"] == []
    assert out["data"]["failed_ids"] == [101]
    assert out["data"]["failed_details"][101]["code"] == "AD_GROUP_MEMBERSHIP_REVOKE_FAILED"
    assert "No governed group bound to READ" in out["data"]["failed_reasons"][101]
    assert [p for p, _ in post_calls] == ["/api/internal/access-requests/item-executions"]
    assert post_calls[0][1]["status"] == "FAILED"


def test_revoke_keeps_the_member_still_granted_by_another_request(monkeypatch) -> None:
    async def _fake_internal_get(path: str):
        if "/other-active" in path:
            return "REQ-77"
        return _revoke_plan([
            {"id": 201, "target_type": "storage_root", "target_id": 77, "permission": "read",
             "access_level_code": "READ", "group_ref": "B2S_ROOT_77_READ", "identity_source_id": 9, "error": None}
        ])

    executions: list[dict] = []

    async def _fake_internal_post(path: str, payload: dict):
        if path == "/api/internal/access-requests/item-executions":
            executions.append(payload)
            return {"ok": True}
        if path == "/api/access-requests/bulk":
            return {"data": {"ok": True, "updated_ids": [101], "failed_ids": []}}
        raise AssertionError(path)

    async def _never_called(*args, **kwargs):
        raise AssertionError("the member must stay in the group")

    fake_routes(monkeypatch, api, get=_fake_internal_get, post=_fake_internal_post)
    monkeypatch.setattr(api, "remove_ad_group_member", _never_called)
    journal = _capture_journal(monkeypatch)

    out = asyncio.run(api.bulk_decision(_Req({"ids": [101], "decision": "revoke"})))

    assert out["data"]["updated_ids"] == [101]
    assert executions[0]["result_json"] == {"kept": True, "still_granted_by": "REQ-77"}
    assert "ad_group_member_kept" in [action for action, _ in journal]
