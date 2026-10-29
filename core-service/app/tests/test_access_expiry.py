from __future__ import annotations

import asyncio

from app.api.governance import access_requests as governance
from app.jobs import access_expiry


class _Db:
    def __init__(self) -> None:
        self.updates: list[int] = []

    def execute(self, statement, params=None):
        if "UPDATE access_requests" in str(statement):
            self.updates.append(int(params["id"]))
        return self

    def mappings(self):
        return self

    def first(self):
        return {"user": "Paul Martin", "root": "corp"}

    def commit(self) -> None:
        pass


def test_expiry_closes_removed_requests_and_waits_after_a_failure(monkeypatch) -> None:
    access_expiry._last_failure.clear()
    db = _Db()
    monkeypatch.setattr(access_expiry, "due_request_ids", lambda db, limit=50: [1, 2])
    monkeypatch.setattr(governance, "_journal", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.activity_log.log_activity", lambda *args, **kwargs: {})

    async def revoke(*, req_id, request, correlation_id):
        assert request.headers["x-roles"] == "platform_admin"
        return "AD unreachable" if req_id == 2 else None

    monkeypatch.setattr(governance, "_revoke_request_memberships", revoke)

    first = asyncio.run(access_expiry.run_access_expiry(db, trigger="schedule"))
    assert first["status"] == "partial"
    assert first["expired_ids"] == [1]
    assert db.updates == [1]
    assert list(first["failed"]) == ["2"]

    # The failed request waits 6 h before the next attempt
    second = asyncio.run(access_expiry.run_access_expiry(db, trigger="schedule"))
    assert second["status"] == "success"
    assert second["waiting_retry"] == [2]
    assert db.updates == [1, 1]
