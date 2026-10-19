from __future__ import annotations

from app.services import storage_root_access_profile_resolution as module


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

