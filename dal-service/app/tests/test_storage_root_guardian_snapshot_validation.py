from __future__ import annotations

import sys

import pytest
from fastapi import HTTPException

if sys.version_info < (3, 10):
    pytest.skip("Requires Python >= 3.10 for SQLAlchemy mapped union annotations", allow_module_level=True)

from app.routers import storage_roots as router


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
    def __init__(
        self,
        *,
        identity_source_id: int | None,
        eligible_identity_ids: list[int],
        existing_guardian_ids: list[int] | None = None,
    ):
        self.identity_source_id = identity_source_id
        self.eligible_identity_ids = eligible_identity_ids
        self.existing_guardian_ids = list(existing_guardian_ids or [])

    def execute(self, query, params=None):
        sql = str(getattr(query, "text", query))
        if "FROM storage_roots sr" in sql and "JOIN storage_endpoints se" in sql:
            return _Rows(first={"identity_source_id": self.identity_source_id})
        if "FROM storage_root_roles srr" in sql and "LOWER(srr.role) = 'guardian'" in sql:
            return _Rows(all_rows=[{"identity_id": v} for v in self.existing_guardian_ids])
        if "FROM directory_snapshots ds" in sql and "directory_snapshot_users dsu" in sql:
            return _Rows(all_rows=[{"identity_id": v} for v in self.eligible_identity_ids])
        return _Rows()


def test_guardian_validation_skips_when_storage_root_has_no_identity_source() -> None:
    db = _FakeDB(identity_source_id=None, eligible_identity_ids=[])
    router._guardians_in_active_snapshot_enabled(
        db,
        storage_root_id=7,
        guardian_ids=[10],
    )


def test_guardian_validation_rejects_id_not_in_active_enabled_snapshot() -> None:
    db = _FakeDB(identity_source_id=9, eligible_identity_ids=[11, 12])

    try:
        router._guardians_in_active_snapshot_enabled(
            db,
            storage_root_id=7,
            guardian_ids=[12, 99],
        )
        assert False, "Expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 400
        assert "Invalid identity ids: 99" in str(exc.detail)


def test_guardian_validation_accepts_when_all_guardians_eligible() -> None:
    db = _FakeDB(identity_source_id=9, eligible_identity_ids=[11, 12])
    router._guardians_in_active_snapshot_enabled(
        db,
        storage_root_id=7,
        guardian_ids=[11, 12],
    )


def test_guardian_ids_requiring_validation_only_returns_new_guardians() -> None:
    db = _FakeDB(
        identity_source_id=9,
        eligible_identity_ids=[11, 12, 13],
        existing_guardian_ids=[11, 12],
    )

    out = router._guardian_ids_requiring_snapshot_validation(
        db,
        storage_root_id=7,
        guardian_ids=[11, 12, 13],
    )

    assert out == [13]


def test_guardian_ids_requiring_validation_keeps_all_when_no_existing_guardians() -> None:
    db = _FakeDB(
        identity_source_id=9,
        eligible_identity_ids=[11, 12],
        existing_guardian_ids=[],
    )

    out = router._guardian_ids_requiring_snapshot_validation(
        db,
        storage_root_id=7,
        guardian_ids=[11, 12],
    )

    assert out == [11, 12]
