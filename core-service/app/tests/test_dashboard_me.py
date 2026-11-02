from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

from app.api import dashboard as api


class _Db:
    def execute(self, *_a, **_k):
        return SimpleNamespace(scalar=lambda: 1)


def _rows(now):
    return [
        {"request_id": 1, "requester_identity_id": 7, "status": "pending", "storage_root_id": 10, "created_at": now},
        {"request_id": 2, "requester_identity_id": 7, "status": "approved", "storage_root_id": 11, "expires_at": now + timedelta(days=5), "latest_execution_status": "FAILED"},
        {"request_id": 3, "requester_identity_id": 8, "status": "pending", "storage_root_id": 20, "overdue": True, "created_at": now},
        {"request_id": 4, "requester_identity_id": 7, "status": "rejected", "storage_root_id": 10, "updated_at": now - timedelta(days=60)},
    ]


def _run(monkeypatch, guarded):
    now = datetime.utcnow()
    monkeypatch.setattr(api, "actor_from_request", lambda _r: SimpleNamespace(identity_id=7, roles=frozenset({"user"})))
    monkeypatch.setattr(api, "get_guardian_storage_root_ids", lambda _db, _actor: guarded)
    monkeypatch.setattr(api, "filter_access_request_rows", lambda _db, _actor, rows: rows)
    monkeypatch.setattr(api, "AccessRequestsViewsRepo", lambda _db: SimpleNamespace(list=lambda **_k: _rows(now)))
    return api.get_user_dashboard_me(SimpleNamespace(), _Db())["data"]


def test_a_user_sees_only_their_own_requests(monkeypatch) -> None:
    data = _run(monkeypatch, [])
    assert data["role"] == "user" and "guardian" not in data
    assert data["mine"] == {"pending": 1, "active": 1, "ending_30d": 1, "failed": 1, "refused_30d": 0}


def test_a_guardian_also_sees_what_to_decide_on_their_folders(monkeypatch) -> None:
    data = _run(monkeypatch, [20])
    assert data["role"] == "guardian"
    assert data["guardian"]["to_decide"] == 1 and data["guardian"]["overdue"] == 1 and data["guardian"]["folders"] == 1
    assert [row["request_id"] for row in data["to_decide"]] == [3]
