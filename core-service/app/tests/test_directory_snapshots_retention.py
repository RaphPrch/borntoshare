from __future__ import annotations

from app.data.repositories.directory_snapshots_repo import DirectorySnapshotsRepo


class _Result:
    def __init__(self, ids):
        self._ids = ids

    def scalars(self):
        return self

    def all(self):
        return list(self._ids)


class _FakeDB:
    def __init__(self, archived_ids):
        self.archived_ids = archived_ids
        self.deletes: list[tuple[str, list[int]]] = []

    def execute(self, stmt, params=None):
        sql = str(stmt)
        if sql.strip().upper().startswith("DELETE"):
            self.deletes.append((sql.split()[2], list(params["ids"])))
            return None
        return _Result(self.archived_ids)


def test_purge_keeps_most_recent_archived_snapshot_detail() -> None:
    db = _FakeDB([30, 20, 10])  # newest first
    purged = DirectorySnapshotsRepo(db).purge_archived_details(identity_source_id=1)

    assert purged == 2
    # memberships first (FK to snapshot groups), header rows untouched
    assert [table for table, _ in db.deletes] == [
        "directory_snapshot_memberships",
        "directory_snapshot_users",
        "directory_snapshot_groups",
    ]
    assert all(ids == [20, 10] for _, ids in db.deletes)


def test_purge_does_nothing_when_within_retention() -> None:
    db = _FakeDB([30])
    assert DirectorySnapshotsRepo(db).purge_archived_details(identity_source_id=1) == 0
    assert db.deletes == []
