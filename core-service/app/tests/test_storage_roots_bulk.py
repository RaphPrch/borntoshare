from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import storage_roots as api


class _Db:
    def __init__(self) -> None:
        self.rollbacks = 0

    def rollback(self) -> None:
        self.rollbacks += 1


def _payload(**extra):
    items = [
        {"storage_endpoint_id": 1, "name": "ok", "root_path": r"\\fs\ok"},
        {"storage_endpoint_id": 1, "name": "taken", "root_path": r"\\fs\taken"},
    ]
    return api.StorageRootBulkPayload(items=items, **extra)


def _setup(monkeypatch):
    def create(payload, request, db, *, inherit_from_parent=False):
        assert inherit_from_parent
        if payload.name == "taken":
            raise HTTPException(status_code=409, detail={"code": "X", "message": "Storage root already exists"})
        return SimpleNamespace(id=7)

    logged = []
    monkeypatch.setattr(api, "_create_storage_root", create)
    monkeypatch.setattr(api, "log_activity", lambda *a, **k: logged.append(k))
    monkeypatch.setattr(api, "actor_from_request", lambda _r: SimpleNamespace(identity_id=1, display_name="a"))

    async def no_check(_root_id):
        return None

    monkeypatch.setattr(api, "_queue_root_check", no_check)
    return logged


def _request():
    return SimpleNamespace(headers={})


def test_a_refused_folder_does_not_stop_the_others_and_is_logged(monkeypatch) -> None:
    logged = _setup(monkeypatch)
    data = asyncio.run(api.create_roots_in_bulk(_payload(), _request(), _Db()))["data"]
    assert [row["id"] for row in data["created"]] == [7]
    assert data["failed"][0]["name"] == "taken" and data["failed"][0]["message"] == "Storage root already exists"
    assert logged[0]["outcome"] == "failure" and logged[0]["action"] == "storage_root.created"


def test_refused_guardians_are_a_warning_on_a_folder_that_exists(monkeypatch) -> None:
    _setup(monkeypatch)

    def refuse(*_a, **_k):
        raise HTTPException(status_code=422, detail={"code": "TOO_FEW_GUARDIANS", "message": "Il faut 2 garants"})

    monkeypatch.setattr(api, "replace_storage_root_owners", refuse)
    data = asyncio.run(api.create_roots_in_bulk(_payload(guardian_ids=[3]), _request(), _Db()))["data"]
    assert data["created"][0]["warnings"] == ["Il faut 2 garants"]


def test_the_catalog_tells_new_from_managed(monkeypatch) -> None:
    endpoint = SimpleNamespace(id=1, name="FS")
    item = api._discovered_item(endpoint, {"root_path": r"\\fs\Compta"}, {api._normalize_root_path(r"\\FS\compta")})
    assert item["managed"] is True and item["name"] == "Compta"
    assert api._discovered_item(endpoint, {"root_path": r"\\fs\RH"}, set())["managed"] is False


def test_an_unexpected_error_on_one_folder_does_not_lose_the_batch(monkeypatch) -> None:
    _setup(monkeypatch)

    def create(payload, request, db, *, inherit_from_parent=False):
        if payload.name == "taken":
            raise RuntimeError("data too long")
        return SimpleNamespace(id=7)

    monkeypatch.setattr(api, "_create_storage_root", create)
    data = asyncio.run(api.create_roots_in_bulk(_payload(), _request(), _Db()))["data"]
    assert [row["id"] for row in data["created"]] == [7]
    assert data["failed"][0]["message"] == "The folder could not be saved"


@pytest.mark.parametrize(
    "path",
    [r"C:\Windows\System32", r"\\fs", r"\\fs\share\..\..\Windows", r"\\fs\C$", r"\\fs\ADMIN$", r"\\fs\ipc$", r"\\fs\SYSVOL", r"\\fs\netlogon\x"],
)
def test_paths_that_cannot_be_managed(path) -> None:
    assert api._root_path_error("smb", path)


@pytest.mark.parametrize("path", [r"\\fs\Compta", r"\\fs\Data$\Sub", "//fs/share/a"])
def test_real_shares_are_accepted(path) -> None:
    assert api._root_path_error("smb", path) is None


def test_guardians_are_added_to_those_the_folder_has(monkeypatch) -> None:
    _setup(monkeypatch)
    seen = {}
    monkeypatch.setattr(api, "_load_existing_guardian_ids", lambda _db, *, storage_root_id: {5})

    def replace(root_id, payload, request, db):
        if root_id == 2:
            raise HTTPException(status_code=422, detail={"code": "TOO_FEW_GUARDIANS", "message": "Il faut 2 garants"})
        seen[root_id] = payload.guardian_ids

    monkeypatch.setattr(api, "replace_storage_root_owners", replace)
    payload = api.StorageRootBulkGuardiansPayload(root_ids=[1, 2], guardian_ids=[3])
    data = api.add_guardians_in_bulk(payload, _request(), _Db())["data"]
    assert seen == {1: [3, 5]} and data["updated"] == [1]
    assert data["failed"] == [{"storage_root_id": 2, "message": "Il faut 2 garants"}]
