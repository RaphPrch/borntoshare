from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.actions import acl

PARAMS = {
    "host": "dc01",
    "share": "projects",
    "path": "",
    "ad_group_name": "LAB_PROJECTS_RW",
    "permission": "write",
    "username": "EXAMPLE\\Administrator",
    "password": "secret",
    "domain": "EXAMPLE",
}

LISTING_WITHOUT_ACE = b"REVISION:1\nACL:Everyone:ALLOWED/0x0/READ\nACL:EXAMPLE\\Administrator:ALLOWED/0x0/FULL\n"


def _fake_smbcacls(monkeypatch, listing_after_add: bytes) -> list[list[str]]:
    calls: list[list[str]] = []

    def run_samba(cmd, **kwargs):
        calls.append(list(cmd))
        return SimpleNamespace(stdout=b"" if "--add" in cmd else listing_after_add, stderr=b"")

    monkeypatch.setattr(acl, "run_samba", run_samba)
    monkeypatch.setattr(acl, "_resolved_ace_principals", lambda **kw: ["EXAMPLE\\LAB_PROJECTS_RW"])
    return calls


def test_ace_read_back_confirms_the_apply(monkeypatch) -> None:
    calls = _fake_smbcacls(monkeypatch, LISTING_WITHOUT_ACE + b"ACL:EXAMPLE\\LAB_PROJECTS_RW:ALLOWED/OI|CI/RWXD\n")

    ok, _message, details = acl.apply_acl_via_group(PARAMS)

    assert ok is True
    assert details["verified"] is True
    assert ["smbcacls", "//dc01/projects", ""] in calls


def test_success_without_the_ace_is_a_failure(monkeypatch) -> None:
    _fake_smbcacls(monkeypatch, LISTING_WITHOUT_ACE)

    ok, _message, details = acl.apply_acl_via_group(PARAMS)

    assert ok is False
    assert any(attempt["stderr"] == "ACE not present after apply" for attempt in details["attempts"])
