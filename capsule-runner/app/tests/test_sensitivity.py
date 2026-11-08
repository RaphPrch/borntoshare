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


def test_listing_gives_the_files_relative_to_the_share():
    files, truncated = sens.list_files(LS, base="Finance")
    assert not truncated
    assert ("Finance\\Mots de passe 2025.xlsx", 12000) in files
    assert ("Finance\\IT\\id_rsa", 1700) in files
    assert len(files) == 6


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

    monkeypatch.setattr(sens.tempfile, "mkdtemp", mkdtemp)
    monkeypatch.setattr(sens, "run_samba", fake_samba)
    ok, message, details = sens.scan_smb_sensitivity({"host": "filer01", "share": "PiloteB2S", "path": "Finance", "username": "u", "password": "p"})
    result = details["sensitivity"]
    assert ok and "4 sensitive" in message
    assert result["counts"] == {"credentials_file": 1, "password": 1, "password_vault": 1, "private_key": 1}
    assert result["files_read"] == 2
    web = next(item for item in result["findings"] if item["path"].endswith("web.config"))
    assert web["line"] == 1 and "S3cr3t" not in web["excerpt"]
    assert workdirs and not os.path.exists(workdirs[0])
