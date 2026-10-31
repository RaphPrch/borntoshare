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


class _MembershipDb:
    def __init__(self) -> None:
        self.deleted: list[tuple[str, dict]] = []
        self.committed = False
        self._row = None

    def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        if sql.startswith("DELETE"):
            self.deleted.append((sql, dict(params)))
        elif "FROM directory_groups" in sql:
            self._row = {"id": 7, "identity_source_id": 3, "external_id": "{g}", "dn": "CN=G", "name": "G"}
        elif "FROM directory_users" in sql:
            self._row = {"id": 9, "external_id": "{u}", "dn": "CN=U"}
        else:
            self._row = None
        return self

    def mappings(self):
        return self

    def first(self):
        return self._row

    def commit(self) -> None:
        self.committed = True


def test_revocation_forgets_only_the_direct_link_in_the_local_directory(monkeypatch) -> None:
    from app.api import access_requests as routes

    monkeypatch.setattr(routes.StorageRootsViewsRepo, "_active_snapshot_id_for_source", lambda self, identity_source_id: 21)
    db = _MembershipDb()

    assert routes.forget_direct_membership(3, "G", "CN=U", "u", db=db) is True

    tables = [sql.split()[2] for sql, _ in db.deleted]
    assert tables == ["directory_effective_memberships", "directory_group_members", "directory_snapshot_memberships"]
    assert "depth = 0" in db.deleted[0][0]
    assert db.deleted[0][1] == {"group_id": 7, "user_id": 9}
    assert db.deleted[2][1]["snapshot_id"] == 21
    assert db.committed is True
