import subprocess

from app.actions import folder


def _done(out: str = "", code: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=code, stdout=out.encode(), stderr=b"")


BASE = {"host": "fs1.example.test", "share": "projects", "username": "svc", "password": "x", "domain": "EXAMPLE"}


def test_share_root_and_parent_references_are_refused(monkeypatch):
    calls = []
    monkeypatch.setattr(folder, "run_samba", lambda cmd, **kw: calls.append(cmd) or _done())
    for path in ("", "/", "..", "a/../..", "."):
        ok, _msg, details = folder.delete_folder({**BASE, "path": path})
        assert ok is False and details["failure_code"] == "FOLDER_PATH_REQUIRED"
        ok, _msg, details = folder.set_folder_inheritance({**BASE, "path": path, "inheritance": "break"})
        assert ok is False
    assert calls == []


def test_break_is_checked_on_the_control_flags(monkeypatch):
    outputs = iter([_done(), _done("REVISION:1\nCONTROL:SR|PD|DP\n")])
    seen = []
    monkeypatch.setattr(folder, "run_samba", lambda cmd, **kw: seen.append(cmd) or next(outputs))
    ok, _msg, details = folder.set_folder_inheritance({**BASE, "path": "corp/finance", "inheritance": "break"})
    assert ok is True and details["inheritance_broken"] is True
    assert seen[0][-1] == "--inherit=copy" and seen[0][2] == "corp\\finance"


def test_restore_that_did_not_apply_fails(monkeypatch):
    outputs = iter([_done(), _done("CONTROL:SR|PD|DP\n")])
    monkeypatch.setattr(folder, "run_samba", lambda cmd, **kw: next(outputs))
    ok, _msg, details = folder.set_folder_inheritance({**BASE, "path": "finance", "inheritance": "restore"})
    assert ok is False and details["failure_code"] == "FOLDER_INHERITANCE_FAILED"


def test_delete_succeeds_only_when_the_folder_is_gone(monkeypatch):
    outputs = iter([_done(), _done("NT_STATUS_NO_SUCH_FILE listing \\finance")])
    monkeypatch.setattr(folder, "run_samba", lambda cmd, **kw: next(outputs))
    assert folder.delete_folder({**BASE, "path": "finance"})[0] is True
    outputs = iter([_done("NT_STATUS_ACCESS_DENIED deleting"), _done("  .  D  0\n")])
    monkeypatch.setattr(folder, "run_samba", lambda cmd, **kw: next(outputs))
    ok, msg, _details = folder.delete_folder({**BASE, "path": "finance"})
    assert ok is False and "ACCESS_DENIED" in msg
