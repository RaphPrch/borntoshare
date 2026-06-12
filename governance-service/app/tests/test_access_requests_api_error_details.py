from __future__ import annotations

import asyncio

from app.api import access_requests as api


class _Req:
    def __init__(self, payload: dict, *, request_id: str = "req_test_err_details") -> None:
        self._payload = payload
        self.headers = {"x-request-id": request_id, "x-identity-id": "7", "x-roles": "user"}

    async def json(self):
        return dict(self._payload)


def test_bulk_decision_approve_exposes_failed_details_from_plan_error(monkeypatch) -> None:
    async def _fake_dal_get(
        path: str,
        timeout: int = 5,
        request_id: str | None = None,
        retries: int = 0,
        extra_headers: dict | None = None,
    ):
        _ = timeout, request_id, retries, extra_headers
        assert path == "/api/internal/access-requests/303/provisioning-plan"
        return {
            "access_request_id": 303,
            "principal": {"dn": "CN=John,OU=Users,DC=example,DC=com", "username": "john"},
            "items": [
                {
                    "id": 401,
                    "target_type": "storage_root",
                    "target_id": 42,
                    "permission": "READ",
                    "access_level_code": "READ",
                    "storage_root_access_profile_id": None,
                    "group_ref": None,
                    "profile_status": None,
                    "group_external_id": None,
                    "identity_source_id": None,
                    "error": "No active storage-root access profile is linked to permission READ.",
                    "error_detail": {
                        "item_id": 401,
                        "code": "STORAGE_ROOT_ACCESS_PROFILE_MISSING",
                        "message": "No active storage-root access profile is linked to permission READ.",
                        "hint": "Attach a READ access profile to this storage root before approval.",
                        "storage_root_id": 42,
                        "requested_permission": "READ",
                        "candidates_count": 0,
                        "repair_attempted": True,
                        "repair_result": "still_missing",
                    },
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
        if path == "/api/internal/access-requests/item-executions":
            return {"ok": True}
        raise AssertionError(path)

    monkeypatch.setattr(api, "dal_get", _fake_dal_get)
    monkeypatch.setattr(api, "dal_post", _fake_dal_post)

    out = asyncio.run(api.bulk_decision(_Req({"ids": [303], "decision": "approve"})))

    assert out["data"]["ok"] is False
    assert out["data"]["failed_ids"] == [303]
    assert int(out["data"]["updated_count"] or 0) == 0
    assert int(out["data"]["executions_started"] or 0) == 0
    failed_details = dict(out["data"].get("failed_details") or {})
    detail = dict(failed_details.get(303) or failed_details.get("303") or {})
    assert detail.get("code") == "STORAGE_ROOT_ACCESS_PROFILE_MISSING"
    assert "Attach a READ access profile" in str(detail.get("hint") or "")
    assert detail.get("repair_attempted") is True
    assert detail.get("repair_result") == "still_missing"
