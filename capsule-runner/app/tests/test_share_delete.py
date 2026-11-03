from __future__ import annotations

from types import SimpleNamespace

from app.actions import folder

BASE = {"host": "files.example.test", "username": "svc", "password": "x", "domain": "EXAMPLE"}
INFO = "netname: Finance\n\tremark: BornToShare\n\tpath: C:\\Shares\\Finance\n"


def _fake(monkeypatch, *outputs):
    calls = []
    queue = list(outputs)

    def run_samba(cmd, **kwargs):
        calls.append(list(cmd))
        return SimpleNamespace(stdout=(queue.pop(0) if queue else "").encode(), stderr=b"", returncode=0)

    monkeypatch.setattr(folder, "run_samba", run_samba)
    return calls


def test_removes_the_share_and_checks_it_is_gone(monkeypatch):
    calls = _fake(monkeypatch, INFO, "", "")
    ok, _, details = folder.delete_share({**BASE, "share": "Finance", "path": "unused"})
    assert ok is True and details["deleted"] is True and details["path"] == "C:\\Shares\\Finance"
    assert calls[1][-1] == 'netsharedel "Finance"'


def test_a_share_that_does_not_exist_is_reported(monkeypatch):
    _fake(monkeypatch, "WERR_NERR_NETNAMENOTFOUND")
    ok, _, details = folder.delete_share({**BASE, "share": "Finance", "path": "unused"})
    assert ok is False and details["failure_code"] == "SHARE_NOT_FOUND"


def test_system_shares_are_never_removed(monkeypatch):
    calls = _fake(monkeypatch)
    for share in ("ADMIN$", "C$", "NETLOGON", "SYSVOL", "bad/name"):
        ok, _, details = folder.delete_share({**BASE, "share": share, "path": "unused"})
        assert ok is False and details["failure_code"] == "SHARE_NAME_INVALID"
    assert calls == []


def test_a_share_still_there_is_a_failure(monkeypatch):
    _fake(monkeypatch, INFO, "result was WERR_ACCESS_DENIED", INFO)
    ok, _, details = folder.delete_share({**BASE, "share": "Finance", "path": "unused"})
    assert ok is False and details["failure_code"] == "SHARE_ADMIN_REQUIRED"


def test_the_empty_folder_goes_with_the_share_when_asked(monkeypatch):
    calls = _fake(monkeypatch, INFO, "", "", "")
    ok, _, details = folder.delete_share({**BASE, "share": "Finance", "path": "unused", "remove_empty_folder": True})
    assert ok is True and details["folder_removed"] is True
    assert calls[3][1] == "//files.example.test/C$" and calls[3][-1] == 'rmdir "Shares\\Finance"'


def test_a_folder_with_files_is_kept(monkeypatch):
    _fake(monkeypatch, INFO, "", "", "NT_STATUS_DIRECTORY_NOT_EMPTY removing remote directory")
    ok, _, details = folder.delete_share({**BASE, "share": "Finance", "path": "unused", "remove_empty_folder": True})
    assert ok is True and details["folder_removed"] is False and details["folder_kept_because"] == "not_empty"
