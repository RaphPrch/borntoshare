from __future__ import annotations

from app.routers import storage_root_bindings_internal as module


class _FakeDB:
    pass


def test_repair_storage_root_bindings_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        module,
        "repair_missing_root_bindings",
        lambda db, storage_root_id, commit=True: type(
            "_R",
            (),
            {
                "to_dict": lambda self: {
                    "storage_root_id": int(storage_root_id),
                    "created_rows": 1,
                    "updated_rows": 0,
                    "deactivated_rows": 0,
                    "unchanged_rows": 0,
                    "repaired": True,
                    "expected_permissions": ["READ", "WRITE"],
                    "missing_permissions": [],
                    "ambiguity_warnings": [],
                    "approval_ready": True,
                }
            },
        )(),
    )

    out = module.repair_storage_root_bindings(storage_root_id=17, db=_FakeDB())
    data = out.get("data") if isinstance(out, dict) and "data" in out else out
    assert int((data or {}).get("storage_root_id") or 0) == 17
    assert bool((data or {}).get("repaired")) is True


def test_resync_zone_root_bindings_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        module,
        "resync_roots_for_zone",
        lambda db, zone_id, replace_stale=True, commit=True: {
            "zone_id": int(zone_id),
            "roots_count": 2,
            "root_ids": [1, 2],
            "reports": [],
            "created_rows": 2,
            "updated_rows": 0,
            "deactivated_rows": 0,
            "unchanged_rows": 0,
            "repaired_roots": 2,
        },
    )

    out = module.resync_zone_root_bindings(zone_id=8, db=_FakeDB())
    data = out.get("data") if isinstance(out, dict) and "data" in out else out
    assert int((data or {}).get("zone_id") or 0) == 8
    assert int((data or {}).get("roots_count") or 0) == 2

