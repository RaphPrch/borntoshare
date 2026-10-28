"""Guards: one snapshot at a time per source, unique source names, one authenticating source per domain."""
from __future__ import annotations

import sys

import pytest
from fastapi import HTTPException

if sys.version_info < (3, 10):
    pytest.skip("Requires Python >= 3.10 for SQLAlchemy mapped union annotations", allow_module_level=True)

from app.api import identity_sources
from app.api import internal_directory_snapshots as snapshots_api
from app.data.repositories import directory_snapshots_repo
from app.schemas.directory_snapshots import DirectorySnapshotRunRequest


class _Rows:
    def __init__(self, rows):
        self._rows = list(rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _DB:
    def __init__(self, *, name_taken=False, domain_taken=False):
        self.name_taken = name_taken
        self.domain_taken = domain_taken
        self.queries: list[str] = []

    def execute(self, statement, params=None):
        sql = " ".join(str(statement).split()).lower()
        self.queries.append(sql)
        if "lower(trim(name))" in sql:
            return _Rows([(9,)] if self.name_taken else [])
        if "lower(trim(domain_name))" in sql:
            return _Rows([("Corp AD",)] if self.domain_taken else [])
        return _Rows([])


def test_a_second_snapshot_of_the_same_source_is_refused(monkeypatch) -> None:
    monkeypatch.setattr(directory_snapshots_repo.DirectorySnapshotsRepo, "running_runs", lambda self, identity_source_id=None: {5: 14})
    monkeypatch.setattr(
        directory_snapshots_repo.DirectorySnapshotsRepo,
        "create_run",
        lambda *a, **kw: pytest.fail("no run may be created while another one is running"),
    )

    with pytest.raises(HTTPException) as exc:
        snapshots_api.create_snapshot_run(
            DirectorySnapshotRunRequest(identity_source_id=5, initiated_by="test", snapshot_source="governance"),
            db=object(),
        )

    assert exc.value.status_code == 409
    assert exc.value.detail["error_code"] == "SNAPSHOT_ALREADY_RUNNING"
    assert exc.value.detail["snapshot_id"] == 14


def test_running_runs_ignore_abandoned_runs() -> None:
    captured = {}

    class _Capture:
        def execute(self, statement, params=None):
            captured["sql"] = " ".join(str(statement).split()).lower()
            captured["params"] = params

            class _R:
                def mappings(self):
                    return self

                def all(self):
                    return [{"identity_source_id": 5, "snapshot_id": 14}]

            return _R()

    out = directory_snapshots_repo.DirectorySnapshotsRepo(_Capture()).running_runs(identity_source_id=5)

    assert out == {5: 14}
    assert "in ('queued', 'running')" in captured["sql"]
    assert captured["params"]["stale_minutes"] == directory_snapshots_repo.SNAPSHOT_RUN_STALE_MINUTES


def test_the_name_of_a_source_is_unique() -> None:
    with pytest.raises(HTTPException) as exc:
        identity_sources.ensure_unique_source(
            _DB(name_taken=True), name="Lab AD", domain_name=None, auth_enabled=False, source_type="ad"
        )

    assert exc.value.status_code == 409
    assert exc.value.detail["error_code"] == "IDENTITY_SOURCE_NAME_TAKEN"


def test_only_one_active_source_authenticates_a_domain() -> None:
    with pytest.raises(HTTPException) as exc:
        identity_sources.ensure_unique_source(
            _DB(domain_taken=True), name="Lab AD 2", domain_name="example.test", auth_enabled=True, source_type="ad"
        )

    assert exc.value.detail["error_code"] == "IDENTITY_SOURCE_DOMAIN_TAKEN"
    assert "Corp AD" in exc.value.detail["message"]


def test_a_source_that_does_not_authenticate_may_share_the_domain() -> None:
    db = _DB(domain_taken=True)

    identity_sources.ensure_unique_source(
        db, name="Lab AD inventory", domain_name="example.test", auth_enabled=False, source_type="ad"
    )

    assert not any("domain_name" in sql for sql in db.queries)
