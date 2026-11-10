from app.data.repositories.directory_snapshots_repo import DirectorySnapshotsRepo


class _Db:
    def __init__(self):
        self.calls = []

    def execute(self, statement, params=None):
        self.calls.append((" ".join(str(statement).split()), params))


def test_identities_follow_the_directory_reading() -> None:
    db = _Db()
    DirectorySnapshotsRepo(db)._sync_identities_with_directory(source_id=2, snapshot_id=9)
    disable, enable = db.calls
    # Disabled when absent from the reading, never on a reading without any user, only the active ones
    assert "SET i.is_active = 0, i.status = 'left_directory'" in disable[0]
    assert "NOT EXISTS (SELECT 1 FROM directory_snapshot_users su WHERE su.snapshot_id = :snapshot_id AND su.external_id = i.external_id)" in disable[0]
    assert "AND EXISTS (SELECT 1 FROM directory_snapshot_users su WHERE su.snapshot_id = :snapshot_id)" in disable[0]
    assert "AND i.is_active = 1" in disable[0]
    # Enabled again only when the reading had disabled it (not one an administrator disabled)
    assert "WHERE i.source_id = :identity_source_id AND i.status = 'left_directory'" in enable[0]
    assert disable[1] == enable[1] == {"identity_source_id": 2, "snapshot_id": 9}
