from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.actions import sensitivity as sens

LS = """  .                                   D        0  Tue Nov  4 10:00:00 2026
  ..                                  D        0  Tue Nov  4 10:00:00 2026
  IT                                  D        0  Mon Nov  3 09:12:00 2026
  Mots de passe 2025.xlsx             A    12000  Mon Nov  3 09:12:00 2026
  rapport.pdf                         A   900000  Mon Nov  3 09:12:00 2026

\\\\Finance\\\\IT
  web.config                          A      400  Mon Nov  3 09:12:00 2026
  coffre.kdbx                         A     3000  Mon Nov  3 09:12:00 2026
  readme.txt                          A       50  Mon Nov  3 09:12:00 2026
  id_rsa                              A     1700  Mon Nov  3 09:12:00 2026
"""

FILES = {
    "Finance\\IT\\web.config": b'<add name="db" connectionString="Server=sql01;User Id=app;Password=S3cr3t!x;" />\n',
    "Finance\\IT\\readme.txt": b"password: ******\nnothing here\n",
}


class FakeStream:
    """stream_samba stand-in: the lines of a listing."""

    def __init__(self, text):
        self.text = text

    def __call__(self, cmd, **_kwargs):
        return self

    def __enter__(self):
        return iter(self.text.splitlines())

    def __exit__(self, *exc):
        return None


def test_listing_gives_the_files_relative_to_the_share(monkeypatch):
    import app.shared.samba_auth as samba_auth

    monkeypatch.setattr(samba_auth, "stream_samba", FakeStream(LS))
    files, truncated = sens._listing_smb(["smbclient"], "Finance", "u", "p", 10)
    assert not truncated
    assert [(path, size) for path, size, _stamp in files if path.endswith(("xlsx", "id_rsa"))] == [
        ("Finance\\Mots de passe 2025.xlsx", 12000), ("Finance\\IT\\id_rsa", 1700)]
    assert len(files) == 6 and all(stamp for _path, _size, stamp in files)


def test_names_and_contents_are_flagged_and_the_secret_is_masked():
    assert sens.name_findings("Finance\\IT\\coffre.kdbx")[0]["category"] == "password_vault"
    assert sens.name_findings("Finance\\Mots de passe 2025.xlsx")[0]["category"] == "credentials_file"
    assert sens.name_findings("Finance\\rapport.pdf") == []
    found = sens.content_findings("x", 'Server=sql01;Password=S3cr3t!x;\n$pwd = "Hunter22"\napi_key = "ABCDEFGHIJKLMNOPQRSTUV"')
    assert [item["category"] for item in found] == ["password", "password", "cloud_key"]
    assert all("S3cr3t" not in item["excerpt"] and "Hunter22" not in item["excerpt"] for item in found)
    assert found[0]["line"] == 1
    assert sens.content_findings("x", "password: ******\npassword=${DB_PASSWORD}") == []
    assert sens.content_findings("k", "-----BEGIN OPENSSH PRIVATE KEY-----")[0]["category"] == "private_key"


def test_the_scan_reads_the_small_text_files_and_deletes_its_copies(monkeypatch):
    workdirs = []
    real_mkdtemp = sens.tempfile.mkdtemp

    def mkdtemp(**kwargs):
        path = real_mkdtemp(**kwargs)
        workdirs.append(path)
        return path

    def fake_samba(cmd, **_kwargs):
        script = cmd[-1]
        if "recurse ON" in script:
            return SimpleNamespace(returncode=0, stdout=LS.encode(), stderr=b"")
        for part in script.split("; "):
            if part.startswith("get "):
                remote, local = part[5:-1].split('" "')
                if remote in FILES:
                    with open(local, "wb") as handle:
                        handle.write(FILES[remote])
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    import app.shared.samba_auth as samba_auth

    monkeypatch.setattr(sens.tempfile, "mkdtemp", mkdtemp)
    monkeypatch.setattr(sens, "run_samba", fake_samba)
    monkeypatch.setattr(samba_auth, "stream_samba", FakeStream(LS))
    ok, message, details = sens.scan_smb_sensitivity({"host": "filer01", "share": "PiloteB2S", "path": "Finance", "username": "u", "password": "p"})
    result = details["sensitivity"]
    assert ok and "4 sensitive" in message
    assert result["counts"] == {"credentials_file": 1, "password": 1, "password_vault": 1, "private_key": 1}
    assert result["files_read"] == 2
    web = next(item for item in result["findings"] if item["path"].endswith("web.config"))
    assert web["line"] == 1 and "S3cr3t" not in web["excerpt"]
    assert workdirs and not os.path.exists(workdirs[0])


def _scan(monkeypatch, listing, **params):
    import app.shared.samba_auth as samba_auth

    reads = []

    def fake_samba(cmd, **_kwargs):
        for part in cmd[-1].split("; "):
            if part.startswith("get "):
                remote, local = part[5:-1].split('" "')
                reads.append(remote)
                with open(local, "wb") as handle:
                    handle.write(FILES.get(remote, b"nothing\n"))
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(sens, "run_samba", fake_samba)
    monkeypatch.setattr(samba_auth, "stream_samba", FakeStream(listing))
    ok, _message, details = sens.scan_smb_sensitivity({"host": "filer01", "share": "S", "path": "Finance", "username": "u", "password": "p",
                                                       "rules_version": sens.RULES_VERSION, **params})
    assert ok
    return details["sensitivity"], reads


INCR = """\\Finance
  old.txt                             A      100  Mon Mar  1 09:00:00 2021
  web.config                          A      400  Mon Nov  2 09:12:00 2026
  new.ini                             A      100  Mon Nov  2 10:00:00 2026
"""


def test_only_the_files_changed_since_the_cursor_are_read_again(monkeypatch):
    from datetime import datetime, timezone

    since = datetime(2026, 1, 1).astimezone(timezone.utc).isoformat()
    result, reads = _scan(monkeypatch, INCR, since=since, known_paths=["Finance\\gone.txt", "Finance\\old.txt"])
    assert reads == ["Finance\\web.config", "Finance\\new.ini"]
    incremental = result["incremental"]
    assert incremental["full"] is False and incremental["complete"] is True and incremental["pending"] == 0
    assert incremental["read_paths"] == reads and incremental["gone_paths"] == ["Finance\\gone.txt"]
    assert incremental["next_cursor"] == ""


def test_a_scan_over_its_budget_goes_on_where_it_stopped(monkeypatch):
    monkeypatch.setattr(sens, "MAX_READ_FILES", 1)
    result, reads = _scan(monkeypatch, INCR)
    incremental = result["incremental"]
    assert incremental["full"] is True and reads == ["Finance\\old.txt"]
    assert incremental["complete"] is False and incremental["pending"] == 2 and incremental["next_cursor"] == "Finance\\old.txt"
    result, reads = _scan(monkeypatch, INCR, since=incremental["next_since"], cursor_path=incremental["next_cursor"])
    assert reads == ["Finance\\web.config"]


def test_new_rules_scan_everything_again(monkeypatch):
    result, reads = _scan(monkeypatch, INCR, since="2026-11-08T00:00:00+00:00", rules_version=sens.RULES_VERSION - 1)
    assert result["incremental"]["full"] is True and len(reads) == 3
