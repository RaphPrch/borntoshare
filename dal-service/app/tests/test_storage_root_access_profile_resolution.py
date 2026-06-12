from __future__ import annotations

from app.services import storage_root_access_profile_resolution as module


class _FakeDB:
    def __init__(self, candidates: list[dict] | None = None):
        self.candidates = list(candidates or [])
        self.repaired = False
        self.commit_calls = 0

    def commit(self):
        self.commit_calls += 1


class _FakeRepo:
    def __init__(self, db):
        self.db = db

    def list_active_storage_root_profile_candidates(self, *, storage_root_id: int, canonical_permission: str) -> list[dict]:
        _ = storage_root_id, canonical_permission
        return list(getattr(self.db, "candidates", []))


def test_looks_like_legacy_duplicated_permission_group_name() -> None:
    assert module._looks_like_legacy_duplicated_permission_group_name(
        group_ref="B2S_FINANCE_READ_READ",
        requested_permission="READ",
    )
    assert module._looks_like_legacy_duplicated_permission_group_name(
        group_ref="B2S_FINANCE_RW_RW",
        requested_permission="WRITE",
    )
    assert not module._looks_like_legacy_duplicated_permission_group_name(
        group_ref="B2S_FINANCE_RX",
        requested_permission="READ",
    )
    assert not module._looks_like_legacy_duplicated_permission_group_name(
        group_ref="B2S_FINANCE_RW",
        requested_permission="WRITE",
    )


def test_normalize_requested_permission_variants() -> None:
    assert module.normalize_requested_permission("read") == "READ"
    assert module.normalize_requested_permission("READ") == "READ"
    assert module.normalize_requested_permission("read_ntfs") == "READ"
    assert module.normalize_requested_permission("read-only") == "READ"
    assert module.normalize_requested_permission("write") == "WRITE"
    assert module.normalize_requested_permission("WRITE") == "WRITE"
    assert module.normalize_requested_permission("write_ntfs") == "WRITE"
    assert module.normalize_requested_permission("modify") == "WRITE"
    assert module.normalize_requested_permission("read_write") == "WRITE"
    assert module.normalize_requested_permission("unknown") is None


def test_resolve_storage_root_access_profile_resolved(monkeypatch) -> None:
    monkeypatch.setattr(module, "StorageRootAccessProfilesRepo", _FakeRepo)
    db = _FakeDB(
        [
            {
                "storage_root_access_profile_id": 901,
                "access_profile_id": 11,
                "access_profile_code": "READ",
                "group_ref": "B2S_ROOT_7_READ",
                "group_name": "B2S_ROOT_7_READ",
                "effective_group_ou_dn": "OU=Groups,DC=example,DC=local",
                "identity_source_id": 3,
                "profile_status": "QUEUED",
                "group_external_id": None,
            }
        ]
    )

    out = module.resolve_storage_root_access_profile(
        db=db,
        storage_root_id=7,
        requested_permission="read",
        target_type="storage_root",
    )

    assert out.status == "resolved"
    assert out.storage_root_access_profile_id == 901
    assert out.access_profile_code == "READ"
    assert out.group_ref == "B2S_ROOT_7_READ"
    assert out.candidates_count == 1


def test_resolve_storage_root_access_profile_missing_binding(monkeypatch) -> None:
    monkeypatch.setattr(module, "StorageRootAccessProfilesRepo", _FakeRepo)
    monkeypatch.setattr(
        module,
        "repair_missing_root_bindings",
        lambda db, storage_root_id, commit=True: type(
            "_R",
            (),
            {"to_dict": lambda self: {"repaired": False}},
        )(),
    )
    db = _FakeDB([])

    out = module.resolve_storage_root_access_profile(
        db=db,
        storage_root_id=8,
        requested_permission="WRITE",
        target_type="storage_root",
    )

    assert out.status == "missing_binding"
    assert out.code == "STORAGE_ROOT_ACCESS_PROFILE_MISSING"
    assert out.candidates_count == 0
    assert out.repair_attempted is True
    assert out.repair_result == "noop"


def test_resolve_storage_root_access_profile_ambiguous_binding(monkeypatch) -> None:
    monkeypatch.setattr(module, "StorageRootAccessProfilesRepo", _FakeRepo)
    monkeypatch.setattr(
        module,
        "repair_missing_root_bindings",
        lambda db, storage_root_id, commit=True: type(
            "_R",
            (),
            {"to_dict": lambda self: {"repaired": False}},
        )(),
    )
    db = _FakeDB(
        [
            {"storage_root_access_profile_id": 1001, "access_profile_id": 21, "access_profile_code": "READ"},
            {"storage_root_access_profile_id": 1002, "access_profile_id": 22, "access_profile_code": "READ"},
        ]
    )

    out = module.resolve_storage_root_access_profile(
        db=db,
        storage_root_id=9,
        requested_permission="READ",
        target_type="storage_root",
    )

    assert out.status == "ambiguous_binding"
    assert out.code == "STORAGE_ROOT_ACCESS_PROFILE_AMBIGUOUS"
    assert out.candidates_count == 2


def test_resolve_storage_root_access_profile_invalid_permission(monkeypatch) -> None:
    monkeypatch.setattr(module, "StorageRootAccessProfilesRepo", _FakeRepo)
    monkeypatch.setattr(
        module,
        "repair_missing_root_bindings",
        lambda db, storage_root_id, commit=True: type(
            "_R",
            (),
            {"to_dict": lambda self: {"repaired": False}},
        )(),
    )
    db = _FakeDB([])

    out = module.resolve_storage_root_access_profile(
        db=db,
        storage_root_id=10,
        requested_permission="execute",
        target_type="storage_root",
    )

    assert out.status == "invalid_permission"
    assert out.code == "INVALID_REQUEST_PERMISSION"


def test_resolve_storage_root_access_profile_inactive_candidate_only_is_missing(monkeypatch) -> None:
    monkeypatch.setattr(module, "StorageRootAccessProfilesRepo", _FakeRepo)
    monkeypatch.setattr(
        module,
        "repair_missing_root_bindings",
        lambda db, storage_root_id, commit=True: type(
            "_R",
            (),
            {"to_dict": lambda self: {"repaired": False}},
        )(),
    )
    # Inactive rows are filtered by repository helper; resolver only sees no candidates.
    db = _FakeDB([])

    out = module.resolve_storage_root_access_profile(
        db=db,
        storage_root_id=11,
        requested_permission="READ",
        target_type="storage_root",
    )

    assert out.status == "missing_binding"
    assert out.code == "STORAGE_ROOT_ACCESS_PROFILE_MISSING"


def test_resolve_storage_root_access_profile_missing_then_repaired(monkeypatch) -> None:
    monkeypatch.setattr(module, "StorageRootAccessProfilesRepo", _FakeRepo)

    def _repair(db, storage_root_id, commit=True):
        db.candidates = [
            {
                "storage_root_access_profile_id": 1201,
                "access_profile_id": 51,
                "access_profile_code": "WRITE",
                "group_ref": "B2S_ROOT_12_WRITE",
                "group_name": "B2S_ROOT_12_WRITE",
                "effective_group_ou_dn": "OU=Groups,DC=example,DC=local",
                "identity_source_id": 4,
                "profile_status": "QUEUED",
                "group_external_id": None,
            }
        ]
        return type("_R", (), {"to_dict": lambda self: {"repaired": True}})()

    monkeypatch.setattr(module, "repair_missing_root_bindings", _repair)

    db = _FakeDB([])
    out = module.resolve_storage_root_access_profile(
        db=db,
        storage_root_id=12,
        requested_permission="WRITE",
        target_type="storage_root",
    )

    assert out.status == "resolved"
    assert out.repair_attempted is True
    assert out.repair_result == "repaired"
    assert out.storage_root_access_profile_id == 1201


def test_resolve_storage_root_access_profile_legacy_single_candidate_triggers_repair(monkeypatch) -> None:
    monkeypatch.setattr(module, "StorageRootAccessProfilesRepo", _FakeRepo)

    db = _FakeDB(
        [
            {
                "storage_root_access_profile_id": 1301,
                "access_profile_id": 61,
                "access_profile_code": "READ",
                "group_ref": "B2S_FINANCE_READ_READ",
                "group_name": "B2S_FINANCE_READ_READ",
                "effective_group_ou_dn": "OU=Groups,DC=example,DC=local",
                "identity_source_id": 5,
                "profile_status": "QUEUED",
                "group_external_id": None,
            }
        ]
    )

    def _repair(_db, storage_root_id, commit=True):
        _ = storage_root_id, commit
        _db.candidates = [
            {
                "storage_root_access_profile_id": 1301,
                "access_profile_id": 61,
                "access_profile_code": "READ",
                "group_ref": "B2S_FINANCE_RX",
                "group_name": "B2S_FINANCE_RX",
                "effective_group_ou_dn": "OU=Groups,DC=example,DC=local",
                "identity_source_id": 5,
                "profile_status": "QUEUED",
                "group_external_id": None,
            }
        ]
        return type("_R", (), {"to_dict": lambda self: {"repaired": True}})()

    monkeypatch.setattr(module, "repair_missing_root_bindings", _repair)

    out = module.resolve_storage_root_access_profile(
        db=db,
        storage_root_id=13,
        requested_permission="READ",
        target_type="storage_root",
    )

    assert out.status == "resolved"
    assert out.group_ref == "B2S_FINANCE_RX"
    assert out.repair_attempted is True
    assert out.repair_result == "repaired"
