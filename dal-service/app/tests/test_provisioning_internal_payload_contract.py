from __future__ import annotations

from types import SimpleNamespace

from fastapi import HTTPException
from pydantic import ValidationError

from app.routers import provisioning_internal as module
from app.routers.provisioning_internal import UpsertStorageRootAccessProfilePayload


def test_upsert_payload_accepts_read_permission_hash() -> None:
    payload = UpsertStorageRootAccessProfilePayload(
        storage_root_id=1,
        access_level_code="READ",
        permission_hash="READ",
        status="CREATED",
    )
    assert payload.permission_hash == "READ"


def test_upsert_payload_rejects_empty_permission_hash() -> None:
    try:
        _ = UpsertStorageRootAccessProfilePayload(
            storage_root_id=1,
            access_level_code="WRITE",
            permission_hash="",
            status="CREATED",
        )
        assert False, "Expected ValidationError"
    except ValidationError:
        pass


def test_upsert_resolves_access_profile_id_when_missing(monkeypatch) -> None:
    created_data: dict = {}

    class _FakeResult:
        def __init__(self, row):
            self._row = row

        def mappings(self):
            return self

        def first(self):
            return self._row

    class _FakeDB:
        def execute(self, statement, params):
            sql = str(statement).lower()
            if "from storage_root_access_profiles" in sql:
                return _FakeResult(None)
            if "from access_profiles" in sql:
                assert params["access_level_code"] == "READ"
                return _FakeResult({"id": 9001})
            return _FakeResult(None)

    class _FakeRepo:
        def __init__(self, _db):
            pass

        def find_by_root_and_permission_hash(self, *, storage_root_id: int, permission_hash: str):
            assert storage_root_id == 1
            assert permission_hash == "READ"
            return None

        def create(self, *, data: dict):
            created_data.update(data)
            return SimpleNamespace(id=321, status="CREATED")

        @staticmethod
        def to_dict(obj) -> dict:
            return {
                "id": int(getattr(obj, "id", 0)),
                "status": str(getattr(obj, "status", "CREATED")),
                "access_profile_id": int(created_data.get("access_profile_id") or 0),
            }

    monkeypatch.setattr(module, "StorageRootAccessProfilesRepo", _FakeRepo)
    monkeypatch.setattr(module, "_write_governance_event", lambda *_args, **_kwargs: None)

    out = module.upsert_storage_root_access_profile(
        UpsertStorageRootAccessProfilePayload(
            storage_root_id=1,
            access_level_code="READ",
            permission_hash="READ",
            group_name="B2S_FINANCE_READ",
            status="CREATED",
        ),
        db=_FakeDB(),
    )

    assert out["created"] is True
    assert created_data["access_profile_id"] == 9001
    assert out["data"]["access_profile_id"] == 9001


def test_upsert_returns_422_when_no_template_matches_level(monkeypatch) -> None:
    class _FakeResult:
        def __init__(self, row):
            self._row = row

        def mappings(self):
            return self

        def first(self):
            return self._row

    class _FakeDB:
        def execute(self, statement, _params):
            sql = str(statement).lower()
            if "from storage_root_access_profiles" in sql:
                return _FakeResult(None)
            if "from access_profiles" in sql:
                return _FakeResult(None)
            return _FakeResult(None)

    class _FakeRepo:
        def __init__(self, _db):
            pass

        def find_by_root_and_permission_hash(self, *, storage_root_id: int, permission_hash: str):
            return None

        def create(self, *, data: dict):
            return SimpleNamespace(id=1, status="CREATED")

        @staticmethod
        def to_dict(obj) -> dict:
            return {"id": int(getattr(obj, "id", 0))}

    monkeypatch.setattr(module, "StorageRootAccessProfilesRepo", _FakeRepo)
    monkeypatch.setattr(module, "_write_governance_event", lambda *_args, **_kwargs: None)

    try:
        _ = module.upsert_storage_root_access_profile(
            UpsertStorageRootAccessProfilePayload(
                storage_root_id=1,
                access_level_code="WRITE",
                permission_hash="WRITE",
                group_name="B2S_FINANCE_WRITE",
                status="CREATED",
            ),
            db=_FakeDB(),
        )
        assert False, "Expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 422
        assert "No access_profiles template found" in str(exc.detail)


def test_upsert_returns_422_when_group_name_missing(monkeypatch) -> None:
    class _FakeResult:
        def __init__(self, row):
            self._row = row

        def mappings(self):
            return self

        def first(self):
            return self._row

    class _FakeDB:
        def execute(self, statement, _params):
            sql = str(statement).lower()
            if "from storage_root_access_profiles" in sql:
                return _FakeResult(None)
            if "from access_profiles" in sql:
                return _FakeResult({"id": 9002})
            return _FakeResult(None)

    class _FakeRepo:
        def __init__(self, _db):
            pass

        def find_by_root_and_permission_hash(self, *, storage_root_id: int, permission_hash: str):
            return None

        def create(self, *, data: dict):
            return SimpleNamespace(id=1, status="CREATED")

        @staticmethod
        def to_dict(obj) -> dict:
            return {"id": int(getattr(obj, "id", 0))}

    monkeypatch.setattr(module, "StorageRootAccessProfilesRepo", _FakeRepo)
    monkeypatch.setattr(module, "_write_governance_event", lambda *_args, **_kwargs: None)

    try:
        _ = module.upsert_storage_root_access_profile(
            UpsertStorageRootAccessProfilePayload(
                storage_root_id=1,
                access_level_code="WRITE",
                permission_hash="WRITE",
                status="CREATED",
            ),
            db=_FakeDB(),
        )
        assert False, "Expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 422
        assert "group_name is required" in str(exc.detail)


def test_write_governance_event_accepts_empty_chain(monkeypatch) -> None:
    captured: dict = {}

    class _FakeResult:
        def mappings(self):
            return self

        def first(self):
            return None

    class _FakeDB:
        def execute(self, statement, params=None):
            sql = str(statement).lower()
            if "select event_hash from governance_events" in sql:
                return _FakeResult()
            if "insert into governance_events" in sql:
                captured.update(params or {})
                return _FakeResult()
            return _FakeResult()

    monkeypatch.setattr(module, "compute_event_hash", lambda prev_hash, payload: "h" * 64)
    monkeypatch.setattr(module, "scrub_secrets", lambda payload: payload)

    module._write_governance_event(
        _FakeDB(),
        event_type="profile_created",
        target_type="storage_root_access_profile",
        target_id=77,
        storage_root_access_profile_id=77,
        status_value="CREATED",
        payload_json={"k": "v"},
        actor_ip="127.0.0.1",
        user_agent="pytest",
    )

    assert captured.get("prev_hash") is None
    assert captured.get("event_hash") == "h" * 64
