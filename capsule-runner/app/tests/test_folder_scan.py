"""The measure of a folder: on the server over WinRM, through SMB when the server cannot be walked on."""
from __future__ import annotations

from app.actions import folder_scan
from app.shared.winrm import WinRMError


def _params(**extra):
    return {"host": "10.0.0.5", "share": "Angers", "path": "Finance", "username": "CORP\\svc", "password": "x", "server_name": "FILER01", **extra}


def test_the_server_walk_is_used_first(monkeypatch) -> None:
    monkeypatch.setattr(folder_scan, "measure", lambda **_: {"method": "server", "bytes": 10, "files": 2, "folders": 1,
                                                             "fingerprints": [{"path": "a", "size": 10, "fingerprint": "f"}]})
    monkeypatch.setattr(folder_scan, "_smb_measure", lambda *_: (_ for _ in ()).throw(AssertionError("no SMB")))
    ok, _message, details = folder_scan.scan_folder(_params())
    assert ok and details["scan_method"] == "server" and details["content_size_bytes"] == 10
    assert details["fingerprints"] and "fingerprints" not in details["content_stats"]


def test_smb_when_winrm_is_refused(monkeypatch) -> None:
    def refused(**_):
        raise WinRMError("WINRM_UNREACHABLE", "port closed")

    monkeypatch.setattr(folder_scan, "measure", refused)
    monkeypatch.setattr(folder_scan, "_smb_measure", lambda *_: {"method": "smb", "bytes": 5, "files": 1, "folders": 0})
    ok, _message, details = folder_scan.scan_folder(_params())
    assert ok and details["scan_method"] == "smb" and details["fallback_reason"].startswith("WINRM_UNREACHABLE")


def test_a_listing_too_long_fails_clearly(monkeypatch) -> None:
    monkeypatch.setattr(folder_scan, "measure", lambda **_: (_ for _ in ()).throw(WinRMError("WINRM_TIMEOUT", "slow")))

    def slow(*_):
        raise TimeoutError

    monkeypatch.setattr(folder_scan, "_smb_measure", slow)
    ok, _message, details = folder_scan.scan_folder(_params(timeout_sec=60))
    assert not ok and details["failure_code"] == "SCAN_TIMEOUT"
