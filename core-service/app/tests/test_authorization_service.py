from __future__ import annotations

from app.services.authorization import (
    ActorContext,
    can_access_request,
    can_review_request,
    can_access_storage_root,
    filter_access_request_rows,
    filter_storage_root_rows,
)


class _FakeResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def mappings(self):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _FakeDB:
    def execute(self, stmt, params=None):
        sql = str(getattr(stmt, "text", stmt)).lower()
        params = dict(params or {})
        if "from storage_root_roles" in sql:
            identity_id = int(params.get("identity_id") or 0)
            if identity_id == 7:
                return _FakeResult([{"root_id": 10}, {"root_id": 12}])
            return _FakeResult([])
        if "from access_requests ar" in sql:
            access_request_id = int(params.get("access_request_id") or 0)
            if access_request_id == 101:
                return _FakeResult([{"access_request_id": 101, "requester_identity_id": 99, "target_type": "storage_root", "target_id": 10}])
            if access_request_id == 102:
                return _FakeResult([{"access_request_id": 102, "requester_identity_id": 7, "target_type": "storage_root", "target_id": 44}])
            return _FakeResult([])
        return _FakeResult([])


def test_guardian_can_access_only_guarded_roots() -> None:
    actor = ActorContext(identity_id=7, roles=frozenset({"user"}))
    db = _FakeDB()

    assert can_access_storage_root(db, actor, 10) is True
    assert can_access_storage_root(db, actor, 11) is False


def test_guardian_can_access_owned_or_guarded_requests() -> None:
    actor = ActorContext(identity_id=7, roles=frozenset({"user"}))
    db = _FakeDB()

    assert can_access_request(db, actor, 101) is True
    assert can_access_request(db, actor, 102) is True
    assert can_access_request(db, actor, 999) is False
    assert can_review_request(db, actor, 101) is True
    assert can_review_request(db, actor, 102) is False


def test_filter_rows_respects_guardian_scope() -> None:
    actor = ActorContext(identity_id=7, roles=frozenset({"user"}))
    db = _FakeDB()

    roots = filter_storage_root_rows(
        db,
        actor,
        [{"storage_root_id": 10}, {"storage_root_id": 11}, {"storage_root_id": 12}],
    )
    requests = filter_access_request_rows(
        db,
        actor,
        [
            {"request_id": 1, "requester_id": 7, "storage_root_id": 44},
            {"request_id": 2, "requester_id": 8, "storage_root_id": 10},
            {"request_id": 3, "requester_id": 8, "storage_root_id": 11},
        ],
    )

    assert [row["storage_root_id"] for row in roots] == [10, 12]
    assert [row["request_id"] for row in requests] == [1, 2]
