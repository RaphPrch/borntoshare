from __future__ import annotations

from types import SimpleNamespace

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.data.models.identity import Identity
from app.data.models.storage_root import StorageRoot
from app.api import storage_roots as router


class _FakeDB:
    def __init__(self) -> None:
        self.committed = False
        self.root = StorageRoot(id=1, name="Research", root_path="\\\\srv\\research")
        self.identities = {
            7: Identity(id=7, username="guardian-7"),
            9: Identity(id=9, username="guardian-9"),
        }

    def get(self, model, key):
        if model is StorageRoot and int(key) == 1:
            return self.root
        if model is Identity:
            return self.identities.get(int(key))
        return None

    def commit(self) -> None:
        self.committed = True


def test_replace_storage_root_owners_uses_actor_from_request_and_returns_owners(monkeypatch) -> None:
    db = _FakeDB()
    captured: dict[str, object] = {}

    class _FakeOwnersRepo:
        def __init__(self, _db) -> None:
            self.db = _db

        def replace_owners(self, *, storage_root_id: int, guardian_ids: list[int], assigned_by: int | None = None) -> None:
            captured["storage_root_id"] = int(storage_root_id)
            captured["guardian_ids"] = list(guardian_ids)
            captured["assigned_by"] = assigned_by

    class _FakeViewsRepo:
        def __init__(self, _db) -> None:
            self.db = _db

        def list_owners(self, storage_root_id: int):
            return [
                {"identity_id": 7, "role": "guardian"},
                {"identity_id": 9, "role": "guardian"},
            ]

    monkeypatch.setattr(router, "_guardians_in_active_snapshot_enabled", lambda *args, **kwargs: None)
    monkeypatch.setattr(router, "_guardian_ids_requiring_snapshot_validation", lambda *args, **kwargs: [7, 9])
    monkeypatch.setattr(router, "_reconcile_storage_root_alerts", lambda *args, **kwargs: None)
    monkeypatch.setattr(router, "_load_existing_guardian_ids", lambda *args, **kwargs: {7})
    monkeypatch.setattr(router, "min_guardians", lambda db: 2)
    monkeypatch.setattr(router, "log_activity", lambda *args, **kwargs: captured.setdefault("activity", kwargs))
    monkeypatch.setattr(router, "StorageRootOwnersRepo", _FakeOwnersRepo)
    monkeypatch.setattr(router, "StorageRootsViewsRepo", _FakeViewsRepo)

    app = FastAPI()
    app.include_router(router.router)
    app.dependency_overrides[router.get_db] = lambda: db

    with TestClient(app) as client:
        res = client.put(
            "/storage-roots/1/owners",
            json={"guardian_ids": [7, 9]},
            headers={
                "x-identity-id": "42",
                "x-actor-display": "Admin Local",
                "x-roles": "platform_admin",
            },
        )

    assert res.status_code == 200
    payload = res.json()
    assert payload["data"]["storage_root_id"] == 1
    assert payload["data"]["owners"] == [
        {"identity_id": 7, "role": "guardian"},
        {"identity_id": 9, "role": "guardian"},
    ]
    assert captured["storage_root_id"] == 1
    assert captured["guardian_ids"] == [7, 9]
    assert captured["assigned_by"] == 42
    activity = captured["activity"]
    assert isinstance(activity, dict)
    assert activity["actor_id"] == 42
    assert activity["actor_display"] == "Admin Local"


def _refused_owners_update(monkeypatch, *, guardian_ids, identity, roles, existing, required=2):
    logged: list[dict] = []

    class _Db:
        def get(self, model, identity_id):
            return SimpleNamespace(id=identity_id, name="Finance", root_path="\\\\f\\s")

    monkeypatch.setattr(router, "require_storage_root_access", lambda *args, **kwargs: None)
    monkeypatch.setattr(router, "_guardians_in_active_snapshot_enabled", lambda *args, **kwargs: None)
    monkeypatch.setattr(router, "_guardian_ids_requiring_snapshot_validation", lambda *args, **kwargs: [])
    monkeypatch.setattr(router, "_load_existing_guardian_ids", lambda *args, **kwargs: set(existing))
    monkeypatch.setattr(router, "min_guardians", lambda db: required)
    monkeypatch.setattr(router, "log_activity", lambda db, **kwargs: logged.append(kwargs))
    monkeypatch.setattr(router, "StorageRootOwnersRepo", _NoWriteRepo)
    monkeypatch.setattr(router, "_reconcile_storage_root_alerts", lambda *args, **kwargs: None)

    app = FastAPI()
    app.include_router(router.router)
    app.dependency_overrides[router.get_db] = lambda: _Db()
    with TestClient(app) as client:
        res = client.put(
            "/storage-roots/1/owners",
            json={"guardian_ids": guardian_ids},
            headers={"x-identity-id": str(identity), "x-actor-display": "Actor", "x-roles": roles},
        )
    return res, logged


class _NoWriteRepo:
    def __init__(self, db):
        self.db = db

    def replace_owners(self, **kwargs):
        raise AssertionError("refused updates must not write")


def test_guardian_cannot_remove_themselves_and_the_attempt_is_logged(monkeypatch) -> None:
    res, logged = _refused_owners_update(monkeypatch, guardian_ids=[8, 9], identity=7, roles="user", existing=[7, 8, 9])
    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "GUARDIAN_SELF_REMOVAL_FORBIDDEN"
    assert logged[0]["outcome"] == "denied"
    assert logged[0]["context_json"]["guardian_ids_requested"] == [8, 9]


def test_a_folder_keeps_the_minimum_of_guardians_even_for_an_administrator(monkeypatch) -> None:
    res, logged = _refused_owners_update(monkeypatch, guardian_ids=[8], identity=7, roles="platform_admin", existing=[8, 9])
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "TOO_FEW_GUARDIANS"
    assert logged[0]["context_json"]["code"] == "TOO_FEW_GUARDIANS"
