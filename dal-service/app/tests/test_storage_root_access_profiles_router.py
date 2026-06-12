from __future__ import annotations

import asyncio
from types import SimpleNamespace

from fastapi import HTTPException

from app.models.access_profile import AccessProfile
from app.models.storage_endpoint import StorageEndpoint
from app.models.storage_root import StorageRoot
from app.models.storage_root_access_profile import StorageRootAccessProfile
from app.routers import storage_roots as storage_roots_router


class _FakeQuery:
    def __init__(self, *, first_result=None, all_result=None):
        self._first_result = first_result
        self._all_result = all_result if all_result is not None else []

    def join(self, *args, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        return self._first_result

    def all(self):
        return self._all_result


class _FakeDB:
    def __init__(self, *, root: StorageRoot, profile: AccessProfile, endpoint: StorageEndpoint):
        self.root = root
        self.profile = profile
        self.endpoint = endpoint
        self.link: StorageRootAccessProfile | None = None

        self.added: list[object] = []
        self.commit_calls = 0
        self.rollback_calls = 0

    def get(self, model, key):
        if model is StorageRoot and int(key) == int(self.root.id):
            return self.root
        if model is AccessProfile and int(key) == int(self.profile.id):
            return self.profile
        if model is StorageEndpoint and int(key) == int(self.endpoint.id):
            return self.endpoint
        return None

    def query(self, *models):
        if len(models) == 1 and models[0] is StorageRootAccessProfile:
            return _FakeQuery(first_result=self.link)
        if len(models) == 2 and models[0] is StorageRootAccessProfile and models[1] is AccessProfile:
            if self.link is None:
                return _FakeQuery(all_result=[])
            return _FakeQuery(all_result=[(self.link, self.profile)])
        return _FakeQuery()

    def execute(self, _stmt, _params=None):
        class _FakeResult:
            def mappings(self_inner):
                return self_inner

            def all(self_inner):
                return []

            def first(self_inner):
                return None

        return _FakeResult()

    def add(self, obj):
        self.added.append(obj)
        if isinstance(obj, StorageRootAccessProfile):
            self.link = obj

    def commit(self):
        self.commit_calls += 1

    def refresh(self, _obj):
        return None

    def rollback(self):
        self.rollback_calls += 1


def _build_root() -> StorageRoot:
    return StorageRoot(id=1, storage_endpoint_id=10, name="Finance", root_path=r"\\files\corp\finance\p1", status="active")


def _build_profile() -> AccessProfile:
    return AccessProfile(
        id=7,
        name="STD_READ",
        code="STD_READ",
        permission="READ",
        active=True,
    )


def _build_endpoint() -> StorageEndpoint:
    return StorageEndpoint(
        id=10,
        zone_id=3,
        name="EP-01",
        endpoint_type="SMB",
        capabilities={},
        status="active",
    )


def test_attach_endpoint_is_system_managed_and_forbidden() -> None:
    root = _build_root()
    profile = _build_profile()
    endpoint = _build_endpoint()
    _ = _FakeDB(root=root, profile=profile, endpoint=endpoint)
    try:
        asyncio.run(
            storage_roots_router.attach_storage_root_access_profile(
                storage_root_id=int(root.id),
                access_profile_id=int(profile.id),
            )
        )
        assert False, "Expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 403


def test_detach_soft_deletes_link_instead_of_hard_delete() -> None:
    root = _build_root()
    profile = _build_profile()
    endpoint = _build_endpoint()
    db = _FakeDB(root=root, profile=profile, endpoint=endpoint)
    db.link = StorageRootAccessProfile(storage_root_id=int(root.id), access_profile_id=int(profile.id), active=True)

    out = storage_roots_router.detach_storage_root_access_profile(
        storage_root_id=int(root.id),
        access_profile_id=int(profile.id),
        db=db,
    )

    assert out["meta"]["storage_root_id"] == int(root.id)
    assert db.link is not None
    assert getattr(db.link, "deleted_at", None) is not None
    assert bool(getattr(db.link, "active", True)) is False


def test_detach_rejects_when_profile_is_inherited() -> None:
    root = _build_root()
    profile = _build_profile()
    endpoint = _build_endpoint()
    db = _FakeDB(root=root, profile=profile, endpoint=endpoint)
    db.link = StorageRootAccessProfile(
        storage_root_id=int(root.id),
        access_profile_id=int(profile.id),
        active=True,
        source="INHERITED",
    )

    try:
        storage_roots_router.detach_storage_root_access_profile(
            storage_root_id=int(root.id),
            access_profile_id=int(profile.id),
            db=db,
        )
        assert False, "Expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 409
