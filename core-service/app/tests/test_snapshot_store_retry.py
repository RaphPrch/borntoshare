"""A directory snapshot stored while another one is (two directories at the same time) may hit a MariaDB
deadlock: the storage is replayed, never lost (the snapshot stayed QUEUED for good)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.exc import OperationalError

from app.api import provisioning_internal as api


class _Db:
    def __init__(self):
        self.rollbacks = 0

    def rollback(self):
        self.rollbacks += 1


def _deadlock():
    return OperationalError("INSERT INTO directory_snapshot_memberships", {}, Exception(1213, "Deadlock found"))


def _run(monkeypatch, failures: int, error=_deadlock):
    calls = {"n": 0}

    class _Repo:
        def __init__(self, _db):
            pass

        def bulk_upsert(self, **_kw):
            calls["n"] += 1
            if calls["n"] <= failures:
                raise error()
            return {"users": 1}

        def patch_status(self, **_kw):
            calls["stored"] = True

    monkeypatch.setattr(api, "DirectorySnapshotsRepo", _Repo)
    monkeypatch.setattr(api, "_extract_directory_snapshot_inputs", lambda **_kw: (136, [], [], []))
    monkeypatch.setattr(api.time, "sleep", lambda _s: None)
    monkeypatch.setattr(api, "DirectoryProjectionService", lambda _db: SimpleNamespace(activate_snapshot=lambda **_kw: None))
    db = _Db()
    api._apply_directory_snapshot_success(db, job_row=SimpleNamespace(payload_json=None, id=1, identity_source_id=0), result_json={})
    return calls, db


def test_a_deadlock_is_replayed_and_the_snapshot_stored(monkeypatch) -> None:
    calls, db = _run(monkeypatch, failures=2)
    assert calls["n"] == 3 and calls.get("stored") and db.rollbacks == 2


def test_a_deadlock_that_persists_is_raised(monkeypatch) -> None:
    with pytest.raises(OperationalError):
        _run(monkeypatch, failures=3)


def test_another_database_error_is_not_replayed(monkeypatch) -> None:
    def gone():
        return OperationalError("SELECT 1", {}, Exception(2013, "Lost connection"))

    with pytest.raises(OperationalError):
        _run(monkeypatch, failures=1, error=gone)
