from __future__ import annotations

import subprocess
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


def _fake_smbcacls(monkeypatch, listing_after_add: bytes, *, listing_before: bytes = LISTING_WITHOUT_ACE,
                   add_times_out: bool = False, read_fails_after_add: bool = False) -> list[list[str]]:
    calls: list[list[str]] = []
    added = []

    def run_samba(cmd, **kwargs):
        calls.append(list(cmd))
        if "--add" in cmd:
            added.append(True)
            if add_times_out:
                raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout"))
            return SimpleNamespace(stdout=b"", stderr=b"")
        if added and read_fails_after_add:
            raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout"))
        return SimpleNamespace(stdout=listing_after_add if added else listing_before, stderr=b"")

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


ACE_LINE = b"ACL:EXAMPLE\\LAB_PROJECTS_RW:ALLOWED/OI|CI/RWXD\n"


def test_an_ace_already_present_is_not_written_again(monkeypatch) -> None:
    calls = _fake_smbcacls(monkeypatch, LISTING_WITHOUT_ACE + ACE_LINE, listing_before=LISTING_WITHOUT_ACE + ACE_LINE)

    ok, message, details = acl.apply_acl_via_group(PARAMS)

    assert ok is True and message == "ACL already present"
    assert details["already_present"] is True and details["applied"] is False
    assert not any("--add" in call for call in calls)


def test_with_propagation_the_apply_runs_even_when_the_folder_has_the_ace(monkeypatch) -> None:
    calls = _fake_smbcacls(monkeypatch, LISTING_WITHOUT_ACE + ACE_LINE, listing_before=LISTING_WITHOUT_ACE + ACE_LINE)

    ok, _message, _details = acl.apply_acl_via_group({**PARAMS, "options": {"propagate": True}})

    assert ok is True
    assert any("--add" in call and "--propagate-inheritance" in call for call in calls)


def test_a_timeout_is_resolved_by_reading_the_acl_back(monkeypatch) -> None:
    _fake_smbcacls(monkeypatch, LISTING_WITHOUT_ACE + ACE_LINE, add_times_out=True)

    ok, message, details = acl.apply_acl_via_group(PARAMS)

    assert ok is True and "confirmed after timeout" in message
    assert details["ace_present_after_timeout"] is True


def test_a_timeout_without_the_ace_is_a_failure(monkeypatch) -> None:
    _fake_smbcacls(monkeypatch, LISTING_WITHOUT_ACE, add_times_out=True)

    ok, message, details = acl.apply_acl_via_group(PARAMS)

    assert ok is False and message == "ACL apply timeout: ACE not present"
    assert details["verified_after_timeout"] is True


def test_a_timeout_never_read_back_says_the_result_is_unknown(monkeypatch) -> None:
    _fake_smbcacls(monkeypatch, LISTING_WITHOUT_ACE, add_times_out=True, read_fails_after_add=True)

    ok, message, details = acl.apply_acl_via_group(PARAMS)

    assert ok is False and "result unknown" in message
    assert details["verified_after_timeout"] is False


def test_a_timeout_with_propagation_is_not_a_success(monkeypatch) -> None:
    _fake_smbcacls(monkeypatch, LISTING_WITHOUT_ACE + ACE_LINE, add_times_out=True)

    ok, message, _details = acl.apply_acl_via_group({**PARAMS, "options": {"propagate": True}})

    assert ok is False and "propagation" in message
