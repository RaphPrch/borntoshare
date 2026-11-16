"""Who reaches a sub-folder and why, from the rights the 5S scanner read: resolved with the directory of the core."""
from __future__ import annotations

from app.services import storage_root_permissions as srp


def test_each_entry_is_resolved_and_the_excessive_ones_are_said(monkeypatch) -> None:
    monkeypatch.setattr(srp, "_extra_broad_names", lambda: frozenset())
    monkeypatch.setattr(srp, "_extra_system_names", lambda: frozenset())
    service = srp.StorageRootPermissions
    monkeypatch.setattr(service, "_root", lambda self, root_id: {"identity_source_id": 2, "endpoint_account": "CORP\\userfiler01"})
    monkeypatch.setattr(service, "_snapshot_at", lambda self, source: "2026-11-16T09:00:00Z")
    monkeypatch.setattr(service, "_group_info", lambda self, name, source: {"name": name} if name == "gg_finance" else None)
    monkeypatch.setattr(service, "group_members", lambda self, name, source: [
        {"username": "jane", "display_name": "Jane", "depth": 0}, {"username": "bob", "display_name": "Bob", "depth": 1}])
    monkeypatch.setattr(service, "_one", lambda self, sql, params: {"username": "bob", "display_name": "Bob", "upn": None} if params["name"] == "bob" else None)
    entries = [
        {"who": "CORP\\GG_Finance", "level": "W", "inherited": True},
        {"who": "CORP\\bob", "level": "F", "inherited": False},
        {"who": "S-1-5-21-1-2-3-1105", "level": "R", "inherited": False},
        {"who": "Tout le monde", "level": "W", "inherited": False},
        {"who": "AUTORITE NT\\Système", "level": "F", "inherited": True},
        {"who": "CORP\\jane", "level": "!W", "inherited": False},
        {"who": "FILER01\\localadmin", "level": "R", "inherited": False},
    ]
    monkeypatch.setattr(service, "_one", lambda self, sql, params: {"username": params["name"], "display_name": params["name"].title(), "upn": None}
                        if params["name"] in ("bob", "jane") else None)
    out = srp.analyze_folder_aces(None, 7, entries)
    kinds = {p["who"]: p["kind"] for p in out["principals"]}
    assert kinds == {"CORP\\GG_Finance": "group", "CORP\\bob": "user", "S-1-5-21-1-2-3-1105": "orphan", "Tout le monde": "broad",
                     "AUTORITE NT\\Système": "system", "CORP\\jane": "user", "FILER01\\localadmin": "unknown"}
    people = {p["username"]: p for p in out["people"]}
    # Bob: through the group (nested) and directly with full control; Jane: through the group but denied
    assert people["bob"]["rights"] == "full" and {v["kind"] for v in people["bob"]["via"]} == {"group", "direct"}
    assert any(v.get("nested") for v in people["bob"]["via"]) and people["jane"]["denied"] is True
    codes = {(f["code"], f["who"]) for f in out["findings"]}
    assert {("ORPHAN_SID", "S-1-5-21-1-2-3-1105"), ("BROAD_WRITE", "Tout le monde"), ("USER_ACE", "CORP\\bob"), ("FULL_CONTROL", "CORP\\bob"),
            ("UNKNOWN_ACCOUNT", "FILER01\\localadmin"), ("DENY_ENTRY", "CORP\\jane")} <= codes
    assert out["people_total"] == 2 and out["snapshot_at"] == "2026-11-16T09:00:00Z"
