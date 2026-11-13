"""Notification centre: one notice per person and key, read state per person, never fails the caller."""
from __future__ import annotations

from app.services import inbox


class _Result:
    def __init__(self, rowcount=1):
        self.rowcount = rowcount


class _Db:
    def __init__(self, fail=False):
        self.calls, self.fail, self.committed, self.rolled = [], fail, False, False

    def execute(self, statement, params=None):
        if self.fail:
            raise RuntimeError("no table")
        self.calls.append((str(statement), params))
        return _Result()

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled = True


def test_push_deduplicates_people_and_skips_bad_ids():
    db = _Db()
    added = inbox.push(db, [3, "3", None, 0, "x", 7], "request:1:created", kind="request", title="T" * 400, link="/a")
    assert added == 2
    assert [params["identity"] for _sql, params in db.calls] == [3, 7]
    assert all("INSERT IGNORE" in sql for sql, _params in db.calls)
    assert len(db.calls[0][1]["title"]) == 300
    assert db.committed


def test_push_unknown_kind_and_severity_fall_back():
    db = _Db()
    inbox.push(db, [1], "k", kind="weird", severity="loud", title="t")
    assert db.calls[0][1]["kind"] == "alert" and db.calls[0][1]["severity"] == "info"


def test_push_never_raises_when_the_table_is_missing():
    db = _Db(fail=True)
    assert inbox.push(db, [1], "k", kind="request", title="t") == 0
    assert db.rolled


def test_mark_read_targets_only_the_person():
    db = _Db()
    inbox.mark_read(db, 5, [9, 9, 4])
    sql, params = db.calls[0]
    assert "identity_id = :identity" in sql and params["identity"] == 5
    assert sorted(v for k, v in params.items() if k.startswith("i") and k != "identity") == [4, 9]
    db = _Db()
    inbox.mark_read(db, 5, None)
    assert "id IN" not in db.calls[0][0]


def test_purge_read_keeps_unread_and_never_raises():
    db = _Db()
    inbox.purge_read(db, 90)
    sql, params = db.calls[0]
    assert "read_at IS NOT NULL" in sql and params["days"] == 90
    assert inbox.purge_read(_Db(fail=True)) == 0


class _Row:
    def __init__(self, values):
        self.values = values

    def first(self):
        return self.values


class _TaskDb(_Db):
    """SELECT returns the requester once; UPDATE clears it."""
    def __init__(self, requester):
        super().__init__()
        self.requester = requester

    def execute(self, statement, params=None):
        sql = str(statement)
        self.calls.append((sql, params))
        if sql.startswith("SELECT t.requested_by_identity"):
            return _Row((self.requester, "Angers") if self.requester else None)
        if "requested_by_identity = NULL" in sql:
            self.requester = None
        return _Result()


def test_tell_requester_tells_once_then_nobody():
    db = _TaskDb(requester=12)
    assert inbox.tell_requester(db, "measure", 4, ok=True, detail="3 fichier(s)")
    insert = [params for sql, params in db.calls if "INSERT IGNORE" in sql][0]
    assert insert["identity"] == 12 and insert["kind"] == "task" and "Angers" in insert["title"] and insert["severity"] == "success"
    assert not inbox.tell_requester(db, "measure", 4, ok=True)


def test_tell_requester_without_requester_or_unknown_task():
    assert not inbox.tell_requester(_TaskDb(requester=None), "sensitivity", 4, ok=False)
    assert not inbox.tell_requester(_TaskDb(requester=3), "other", 4, ok=True)
