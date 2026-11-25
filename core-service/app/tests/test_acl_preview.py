"""Dry run of an approval on the NTFS permissions: the ACL as last read, the entry added and the risks."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from app.services import acl_preview, storage_root_permissions


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def __iter__(self):
        return iter(self.rows)


class _Db:
    def __init__(self, root, managed=()):
        self.root, self.managed = root, managed
        self.writes = []

    def execute(self, statement, params=None):
        sql = str(statement)
        if not sql.lstrip().upper().startswith("SELECT"):
            self.writes.append(sql)
        if "storage_root_access_profiles" in sql:
            return _Result([(name,) for name in self.managed])
        return _Result([self.root] if self.root else [])


def _root(permissions, *, path="\\\\filer01\\corp\\finance", days=0, control="SR|DI"):
    read_at = (datetime.now(timezone.utc) - timedelta(days=days)).replace(tzinfo=None).isoformat()
    return {"root_path": path, "endpoint_account": "CORP\\svc-b2s-files",
            "discovered_permissions_json": json.dumps({"discovered_at": read_at, "control": control, "permissions": permissions})}


SYSTEM = [{"principal": "NT AUTHORITY\\SYSTEM", "raw": "ALLOWED/OI|CI/FULL"}, {"principal": "BUILTIN\\Administrators", "raw": "ALLOWED/OI|CI/FULL"}]


def _no_extra_names(monkeypatch):
    monkeypatch.setattr(storage_root_permissions, "_extra_broad_names", lambda: frozenset())
    monkeypatch.setattr(storage_root_permissions, "_extra_system_names", lambda: frozenset())


def test_a_new_group_is_an_entry_added_and_nothing_is_written(monkeypatch) -> None:
    _no_extra_names(monkeypatch)
    db = _Db(_root(SYSTEM))
    out = acl_preview.preview(db, 4, "B2S_FIN_RX", "READ")
    assert out["change"] == "add" and out["target"]["rights"] == "read" and out["risks"] == []
    assert [e["kind"] for e in out["current"]] == ["system", "system"]
    assert db.writes == []  # a dry run


def test_a_group_already_there_or_at_a_lower_level(monkeypatch) -> None:
    _no_extra_names(monkeypatch)
    present = acl_preview.preview(_Db(_root(SYSTEM + [{"principal": "CORP\\B2S_FIN_RW", "raw": "ALLOWED/OI|CI/RWXD"}])), 4, "B2S_FIN_RW", "WRITE")
    assert present["change"] == "present"
    lower = acl_preview.preview(_Db(_root(SYSTEM + [{"principal": "CORP\\B2S_FIN_RW", "raw": "ALLOWED/OI|CI/READ"}])), 4, "B2S_FIN_RW", "WRITE")
    assert lower["change"] == "level_change" and lower["change_from"] == "read"


def test_the_risks_are_named(monkeypatch) -> None:
    _no_extra_names(monkeypatch)
    perms = SYSTEM + [
        {"principal": "Everyone", "raw": "ALLOWED/OI|CI/READ"},
        {"principal": "CORP\\jdupont", "raw": "ALLOWED/0x0/FULL"},
        {"principal": "CORP\\interns", "raw": "DENIED/OI|CI/FULL"},
    ]
    out = acl_preview.preview(_Db(_root(perms, path="\\\\filer01\\corp", days=30, control="SR|PD")), 4, "B2S_CORP_RW", "WRITE")
    codes = {r["code"]: r["values"] for r in out["risks"]}
    assert set(codes) == {"SHARE_ROOT_WRITE", "ACL_READ_OLD", "BROAD_ACCESS", "MANUAL_ENTRIES", "DENY_ENTRIES", "INHERITANCE_BROKEN"}
    assert codes["ACL_READ_OLD"]["days"] == 30 and codes["MANUAL_ENTRIES"]["names"] == ["CORP\\jdupont"]


def test_a_folder_never_read_cannot_be_compared(monkeypatch) -> None:
    _no_extra_names(monkeypatch)
    root = {"root_path": "\\\\filer01\\corp\\hr", "endpoint_account": None, "discovered_permissions_json": None}
    out = acl_preview.preview(_Db(root), 5, "B2S_HR_RX", "READ")
    assert out["change"] == "unknown" and [r["code"] for r in out["risks"]] == ["ACL_NOT_READ"] and out["read_at"] is None


def test_a_group_managed_by_borntoshare_is_not_a_manual_entry(monkeypatch) -> None:
    _no_extra_names(monkeypatch)
    perms = SYSTEM + [{"principal": "CORP\\B2S_FIN_RX", "raw": "ALLOWED/OI|CI/READ"}]
    out = acl_preview.preview(_Db(_root(perms), managed=["B2S_FIN_RX"]), 4, "B2S_FIN_RW", "WRITE")
    assert out["change"] == "add" and out["risks"] == []
