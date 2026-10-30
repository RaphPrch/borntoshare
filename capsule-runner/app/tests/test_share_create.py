from __future__ import annotations

from types import SimpleNamespace

from app.actions import folder

BASE = {"host": "files.example.test", "username": "svc", "password": "x", "domain": "EXAMPLE"}


def _fake(monkeypatch, *outputs):
    calls = []
    queue = list(outputs)

    def run_samba(cmd, **kwargs):
        calls.append(list(cmd))
        return SimpleNamespace(stdout=(queue.pop(0) if queue else "").encode(), stderr=b"", returncode=0)

    monkeypatch.setattr(folder, "run_samba", run_samba)
    return calls


def test_creates_the_folder_tree_then_the_share_and_reads_it_back(monkeypatch):
    calls = _fake(monkeypatch, "", "", "", r"path: C:\\Shares\\Finance".replace("\\\\", chr(92)), "", "", "", "", "ACL:S-1-5-32-544:ALLOWED/OI|CI/FULL")
    ok, _, details = folder.create_share({**BASE, "share": "Finance", "path": r"C:\Shares\Finance"})
    assert ok is True and details["created"] is True
    assert calls[1][1] == "//files.example.test/C$"
    assert 'mkdir "Shares"; mkdir "Shares\\Finance"' in calls[1][3]
    assert '"Finance" -1 ' in calls[2][3]


def test_an_account_without_rights_gets_a_clear_message(monkeypatch):
    _fake(monkeypatch, "", "tree connect failed: NT_STATUS_ACCESS_DENIED")
    ok, message, details = folder.create_share({**BASE, "share": "Finance", "path": r"C:\Shares\Finance"})
    assert ok is False and details["failure_code"] == "SHARE_ADMIN_REQUIRED" and "local administrator" in message


def test_an_existing_share_is_reported(monkeypatch):
    _fake(monkeypatch, "netname: Finance")
    ok, _, details = folder.create_share({**BASE, "share": "Finance", "path": r"C:\Shares\Finance"})
    assert ok is False and details["failure_code"] == "SHARE_EXISTS"


def test_invalid_names_and_paths_reach_nothing(monkeypatch):
    calls = _fake(monkeypatch)
    for share, path, code in (("a$", r"C:\x", "SHARE_NAME_INVALID"), ("a/b", r"C:\x", "SHARE_NAME_INVALID"), ("ok", "relative", "SHARE_PATH_INVALID"), ("ok", r"C:\a\..\:b", "SHARE_PATH_INVALID")):
        assert folder.create_share({**BASE, "share": share, "path": path})[2]["failure_code"] == code
    assert calls == []


def test_a_folder_still_open_to_users_is_a_failure(monkeypatch):
    _fake(monkeypatch, "", "", "", r"path: C:\\Shares\\Finance".replace("\\\\", chr(92)), "", "", "", "", "ACL:S-1-5-32-544:x ACL:S-1-5-32-545:x")
    ok, _, details = folder.create_share({**BASE, "share": "Finance", "path": r"C:\Shares\Finance"})
    assert ok is False and details["failure_code"] == "SHARE_ACL_FAILED"
