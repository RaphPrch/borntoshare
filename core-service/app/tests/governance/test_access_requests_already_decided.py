from __future__ import annotations

import asyncio

from app.api.governance import access_requests as api
from app.tests.governance.route_fakes import fake_routes


class _Req:
    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.headers = {"x-request-id": "req_decided", "x-identity-id": "7", "x-roles": "platform_admin"}

    async def json(self):
        return dict(self._payload)


def _unexpected(path, payload=None):
    raise AssertionError(f"nothing should run: {path}")


def test_approving_a_decided_request_runs_nothing(monkeypatch) -> None:
    for status in ("approved", "executed", "rejected", "revoked"):
        fake_routes(monkeypatch, api, get=_unexpected, post=_unexpected, statuses={5: status})
        out = asyncio.run(api.bulk_decision(_Req({"ids": [5], "decision": "approve"})))["data"]
        assert out["failed_ids"] == [5]
        assert out["failed_details"][5]["code"] == "REQUEST_ALREADY_DECIDED"
        assert int(out["executions_started"]) == 0


def test_rejecting_an_applied_request_does_not_hide_the_access(monkeypatch) -> None:
    fake_routes(monkeypatch, api, get=_unexpected, post=_unexpected, statuses={5: "approved"})
    out = asyncio.run(api.bulk_decision(_Req({"ids": [5], "decision": "reject"})))["data"]
    assert out["failed_ids"] == [5]
    assert out["updated_ids"] == []


def test_a_request_being_approved_is_not_approved_twice(monkeypatch) -> None:
    fake_routes(monkeypatch, api, get=_unexpected, post=_unexpected)
    monkeypatch.setattr(api, "_approvals_in_progress", {5})
    out = asyncio.run(api.bulk_decision(_Req({"ids": [5], "decision": "approve"})))["data"]
    assert out["failed_ids"] == [5]
    assert api._approvals_in_progress == {5}
