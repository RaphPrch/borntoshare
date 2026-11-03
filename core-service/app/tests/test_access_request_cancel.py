from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import access_requests as api


class _Db:
    def __init__(self, row):
        self.row = row
        self.updates = []

    def execute(self, statement, params=None):
        sql = str(statement)
        if sql.startswith("UPDATE"):
            self.updates.append(params)
            return SimpleNamespace()
        row = self.row
        return SimpleNamespace(mappings=lambda: SimpleNamespace(first=lambda: row))

    def commit(self):
        pass

    def rollback(self):
        pass


def _setup(monkeypatch, identity_id):
    logged = []
    monkeypatch.setattr(api, "actor_from_request", lambda _r: SimpleNamespace(identity_id=identity_id, display_name="me"))
    monkeypatch.setattr(api, "log_activity", lambda *a, **k: logged.append(k))
    monkeypatch.setattr(api, "_request_event_labels", lambda db, rid: {"root": "Finance", "storage_root_id": 0})
    return logged


def test_the_requester_cancels_a_pending_request(monkeypatch) -> None:
    logged = _setup(monkeypatch, 5)
    db = _Db({"id": 9, "requester_identity_id": 5, "status": "pending"})
    api.cancel_access_request(9, SimpleNamespace(headers={}), db)
    assert db.updates and db.updates[0]["id"] == 9
    assert logged[0]["action"] == "access_request.cancelled"


def test_someone_else_or_a_decided_request_is_refused(monkeypatch) -> None:
    _setup(monkeypatch, 6)
    with pytest.raises(HTTPException) as other:
        api.cancel_access_request(9, SimpleNamespace(headers={}), _Db({"id": 9, "requester_identity_id": 5, "status": "pending"}))
    assert other.value.status_code == 403
    _setup(monkeypatch, 5)
    with pytest.raises(HTTPException) as decided:
        api.cancel_access_request(9, SimpleNamespace(headers={}), _Db({"id": 9, "requester_identity_id": 5, "status": "approved"}))
    assert decided.value.status_code == 409
