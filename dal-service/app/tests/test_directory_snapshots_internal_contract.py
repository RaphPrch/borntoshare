from __future__ import annotations

import datetime as dt

import app.repositories.directory_snapshots_repo as directory_snapshots_repo_module
from app.repositories.directory_snapshots_repo import DirectorySnapshotsRepo, _coerce_mysql_datetime


class _Rows:
    def __init__(self, first=None, all_rows=None):
        self._first = first
        self._all = all_rows or []

    def mappings(self):
        return self

    def first(self):
        return self._first

    def all(self):
        return list(self._all)


class _FakeDB:
    def __init__(self):
        self.calls = []
        self._commits = 0

    def execute(self, query, params=None):
        sql = str(getattr(query, "text", query))
        raw = params or {}
        p = raw if isinstance(raw, dict) else {}

        if isinstance(raw, list):
            stored_params = [dict(item) for item in raw]
        elif isinstance(raw, dict):
            stored_params = dict(raw)
        else:
            stored_params = raw
        self.calls.append((sql, stored_params))

        if "COALESCE(MAX(version), 0) + 1 AS next_version" in sql:
            return _Rows(first={"next_version": 4})

        if "FROM directory_snapshots" in sql and "WHERE id = :id" in sql:
            return _Rows(
                first={
                    "id": int(p.get("id") or 0),
                    "identity_source_id": 9,
                    "version": 4,
                    "status": "RUNNING",
                    "snapshot_source": "governance",
                    "initiated_by": "gov",
                    "correlation_id": "corr-1",
                    "started_at": None,
                    "finished_at": None,
                    "activated_at": None,
                    "archived_at": None,
                    "summary_json": None,
                    "error_message": None,
                    "created_at": None,
                    "updated_at": None,
                }
            )

        if "WHERE identity_source_id = :identity_source_id" in sql and "AND version = :version" in sql:
            return _Rows(
                first={
                    "id": 44,
                    "identity_source_id": int(p.get("identity_source_id") or 0),
                    "version": int(p.get("version") or 0),
                    "status": "RUNNING",
                    "snapshot_source": "governance",
                    "initiated_by": "gov",
                    "correlation_id": "corr-1",
                    "started_at": None,
                    "finished_at": None,
                    "activated_at": None,
                    "archived_at": None,
                    "summary_json": None,
                    "error_message": None,
                    "created_at": None,
                    "updated_at": None,
                }
            )

        if "FROM directory_snapshots" in sql and "ORDER BY id DESC" in sql:
            return _Rows(
                all_rows=[
                    {
                        "id": 44,
                        "identity_source_id": 9,
                        "version": 4,
                        "status": p.get("status") or "RUNNING",
                    }
                ]
            )

        if "FROM directory_snapshot_users" in sql and "principal_type" in sql:
            return _Rows(
                all_rows=[
                    {
                        "principal_type": "user",
                        "external_id": "CN=Alice,OU=Users,DC=corp,DC=local",
                        "display_name": "Alice",
                        "username": "alice",
                        "email": "alice@corp.local",
                        "dn": "CN=Alice,OU=Users,DC=corp,DC=local",
                        "object_sid": "S-1-5-21-100",
                        "upn": "alice@corp.local",
                        "is_active": 1,
                    }
                ]
            )

        if "FROM directory_snapshot_groups" in sql and "principal_type" in sql:
            return _Rows(
                all_rows=[
                    {
                        "principal_type": "group",
                        "external_id": "CN=B2S_READ,OU=Groups,DC=corp,DC=local",
                        "display_name": "B2S_READ",
                        "username": "B2S_READ",
                        "email": None,
                        "dn": "CN=B2S_READ,OU=Groups,DC=corp,DC=local",
                        "object_sid": None,
                        "upn": None,
                    }
                ]
            )

        if "SELECT COUNT(*) FROM directory_snapshot_users" in sql:
            users_count = sum(
                len(params_batch)
                for statement, params_batch in self.calls
                if "INSERT INTO directory_snapshot_users" in statement and isinstance(params_batch, list)
            )
            groups_count = sum(
                len(params_batch)
                for statement, params_batch in self.calls
                if "INSERT INTO directory_snapshot_groups" in statement and isinstance(params_batch, list)
            )
            memberships_count = sum(
                len(params_batch)
                for statement, params_batch in self.calls
                if "INSERT INTO directory_snapshot_memberships" in statement and isinstance(params_batch, list)
            )
            return _Rows(
                first={
                    "users": int(users_count),
                    "groups": int(groups_count),
                    "memberships": int(memberships_count),
                }
            )

        return _Rows()

    def commit(self):
        self._commits += 1


def test_create_run_returns_new_version_row() -> None:
    db = _FakeDB()
    repo = DirectorySnapshotsRepo(db)

    row = repo.create_run(
        identity_source_id=9,
        initiated_by="gov",
        snapshot_source="governance",
        correlation_id="corr-1",
    )

    assert int(row["id"]) == 44
    assert int(row["identity_source_id"]) == 9
    assert int(row["version"]) == 4
    assert row["status"] == "RUNNING"
    assert db._commits == 1


def test_list_runs_status_filter_is_normalized() -> None:
    db = _FakeDB()
    repo = DirectorySnapshotsRepo(db)

    rows = repo.list_runs(identity_source_id=9, status="running", limit=20)

    assert len(rows) == 1
    assert rows[0]["id"] == 44
    assert rows[0]["identity_source_id"] == 9


def test_search_combines_users_and_groups() -> None:
    db = _FakeDB()
    repo = DirectorySnapshotsRepo(db)

    out = repo.search(
        snapshot_id=44,
        query="b2s",
        principal_type="all",
        base_dn=None,
        search_scope="subtree",
        limit=10,
    )

    assert len(out) == 2
    assert {row["principal_type"] for row in out} == {"user", "group"}


def test_search_normalizes_base_dn_with_spaces() -> None:
    db = _FakeDB()
    repo = DirectorySnapshotsRepo(db)

    out = repo.search(
        snapshot_id=44,
        query="",
        principal_type="all",
        base_dn="DC=corp, DC=local",
        search_scope="subtree",
        limit=10,
    )

    assert len(out) == 2

    user_query_params = [
        params
        for sql, params in db.calls
        if "FROM directory_snapshot_users" in sql and "principal_type" in sql
    ]
    assert user_query_params
    assert user_query_params[0]["base_dn"] == "DC=corp,DC=local"
    assert user_query_params[0]["base_like"] == "%,DC=corp,DC=local"


def test_search_users_supports_enabled_only_filter() -> None:
    db = _FakeDB()
    repo = DirectorySnapshotsRepo(db)

    _ = repo.search(
        snapshot_id=44,
        query="",
        principal_type="user",
        base_dn=None,
        search_scope="subtree",
        limit=10,
        enabled_only=True,
    )

    user_queries = [
        sql
        for sql, _params in db.calls
        if "FROM directory_snapshot_users" in sql and "principal_type" in sql
    ]
    assert user_queries
    assert "AND is_active = 1" in user_queries[0]


def test_coerce_mysql_datetime_accepts_iso_z_and_returns_naive_utc() -> None:
    parsed, invalid = _coerce_mysql_datetime("2026-03-16T13:57:35Z")

    assert invalid is False
    assert parsed == dt.datetime(2026, 3, 16, 13, 57, 35)


def test_coerce_mysql_datetime_accepts_offset_and_normalizes_to_utc() -> None:
    parsed, invalid = _coerce_mysql_datetime("2026-03-16T14:57:35+01:00")

    assert invalid is False
    assert parsed == dt.datetime(2026, 3, 16, 13, 57, 35)


def test_coerce_mysql_datetime_accepts_ldap_generalized_time() -> None:
    parsed, invalid = _coerce_mysql_datetime("20260316135735.0Z")

    assert invalid is False
    assert parsed == dt.datetime(2026, 3, 16, 13, 57, 35)


def test_bulk_upsert_normalizes_iso_z_before_insert() -> None:
    db = _FakeDB()
    repo = DirectorySnapshotsRepo(db)

    out = repo.bulk_upsert(
        snapshot_id=44,
        users=[{"external_id": "u1", "when_changed": "2026-03-16T13:57:35Z"}],
        groups=[],
        memberships=[],
    )

    user_batches = [
        params
        for sql, params in db.calls
        if "INSERT INTO directory_snapshot_users" in sql and isinstance(params, list)
    ]
    assert user_batches
    assert user_batches[0][0]["when_changed"] == dt.datetime(2026, 3, 16, 13, 57, 35)
    assert out["users"] == 1


def test_bulk_upsert_invalid_when_changed_falls_back_to_null_and_logs_warning() -> None:
    warnings: list[dict[str, object]] = []

    def _capture_warning(message: str, *args, **kwargs) -> None:  # pragma: no cover - callback
        warnings.append({"message": message, "extra": kwargs.get("extra")})

    original_warning = directory_snapshots_repo_module.logger.warning
    directory_snapshots_repo_module.logger.warning = _capture_warning
    try:
        db = _FakeDB()
        repo = DirectorySnapshotsRepo(db)

        out = repo.bulk_upsert(
            snapshot_id=44,
            users=[{"external_id": "u1", "when_changed": "not-a-date"}],
            groups=[{"external_id": "g1", "when_changed": "still-not-a-date"}],
            memberships=[],
        )
    finally:
        directory_snapshots_repo_module.logger.warning = original_warning

    user_batches = [
        params
        for sql, params in db.calls
        if "INSERT INTO directory_snapshot_users" in sql and isinstance(params, list)
    ]
    group_batches = [
        params
        for sql, params in db.calls
        if "INSERT INTO directory_snapshot_groups" in sql and isinstance(params, list)
    ]

    assert user_batches
    assert group_batches
    assert user_batches[0][0]["when_changed"] is None
    assert group_batches[0][0]["when_changed"] is None
    assert out["users"] == 1
    assert out["groups"] == 1

    assert len(warnings) == 2
    assert all(isinstance(item.get("extra"), dict) for item in warnings)
    assert all((item.get("extra") or {}).get("snapshot_id") == 44 for item in warnings)
    assert all((item.get("extra") or {}).get("invalid_when_changed_count") == 1 for item in warnings)
