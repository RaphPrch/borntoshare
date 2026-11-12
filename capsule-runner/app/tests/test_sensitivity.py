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


# Numbers built for the test (valid checksums), not real ones
_CARD = "4970101234567893"
_NIR = "185057800608491"
_IBAN = "FR76 3000 6000 0112 3456 7890 189"


def test_personal_and_bank_data_are_found_and_masked() -> None:
    text = (f"client;iban;carte\nDupont;{_IBAN};{_CARD[:4]} {_CARD[4:8]} {_CARD[8:12]} {_CARD[12:]}\n"
            f"secu : {_NIR[0]} {_NIR[1:3]} {_NIR[3:5]} {_NIR[5:7]} {_NIR[7:10]} {_NIR[10:13]} {_NIR[13:]}\n"
            "commande 2026-11-10 ref 1234567890123 tel 0612345678\n"
            "FR76 3000 6000 0112 3456 7890 188\n")
    found = sens.content_findings("\\\\srv\\RH\\export.csv", text)
    assert [(item["category"], item["line"]) for item in found] == [("bank_data", 2), ("personal_data", 3)]
    # Nothing of a number left in an excerpt: the IBAN keeps its country, the card its network, the NIR nothing
    assert found[0]["excerpt"] == "Dupont;FR76••••••;4970••••••"
    assert found[1]["excerpt"] == "secu : ••••••"


def test_checksums_refuse_look_alikes() -> None:
    assert sens._iban_ok(_IBAN) and not sens._iban_ok(_IBAN[:-1] + "8")
    assert sens._luhn_ok(_CARD) and not sens._luhn_ok(_CARD[:-1] + "4")
    assert not sens._luhn_ok("1234567890123")  # an order reference
    assert sens._nir_ok(_NIR) and not sens._nir_ok(_NIR[:-2] + "92")


def test_a_password_line_also_masks_the_numbers_it_holds() -> None:
    found = sens.content_findings("x.txt", f"password=Sup3rSecret iban {_IBAN}")
    assert found[0]["category"] == "password" and _IBAN not in found[0]["excerpt"] and "FR76••••••" in found[0]["excerpt"]


def test_risky_files_by_their_name() -> None:
    category = lambda name: [item["category"] for item in sens.name_findings(f"\\\\srv\\Data\\{name}")]  # noqa: E731
    assert category("base.bak") == ["backup_database"] and category("Archive.pst") == ["mailbox"]
    assert category("setup.exe") == ["executable"] and category("deploy.ps1") == ["executable"]
    assert category("Thumbs.db") == [] and category("rapport.pdf") == []
    assert category("mots de passe.xlsx") == ["credentials_file"]


CACLS = """REVISION:1
CONTROL:SR|DI|DP
OWNER:BUILTIN\\Administrateurs
GROUP:CORP\\Utilisateurs du domaine
ACL:AUTORITE NT\\Système:ALLOWED/I/FULL
ACL:BUILTIN\\Utilisateurs:ALLOWED/I/READ
ACL:CORP\\GG_Finance_RW:ALLOWED/0x0/CHANGE
ACL:CORP\\stagiaire:DENIED/0x10/0x001301bf
"""


def test_a_file_acl_says_who_can_open_it_and_whether_everyone_can():
    acl = sens.parse_cacls(CACLS)
    assert acl["x"] is False and acl["o"] == "BUILTIN\\Administrateurs" and acl["broad"] is True
    assert acl["by"] == ["BUILTIN\\Utilisateurs"]
    assert acl["e"] == ["AUTORITE NT\\Système|F|i", "BUILTIN\\Utilisateurs|R|i", "CORP\\GG_Finance_RW|W|", "!CORP\\stagiaire|W|i"]
    own = sens.parse_cacls("CONTROL:SR|PD|DP\nACL:CORP\\GG_Finance_RW:ALLOWED/0x0/RWXD\n")
    assert own["x"] is True and own["broad"] is False and own["e"] == ["CORP\\GG_Finance_RW|W|"]
    assert sens.parse_cacls("NT_STATUS_ACCESS_DENIED") is None
    assert sens.is_broad("CORP\\Domain Users") and not sens.is_broad("CORP\\GG_Users_Finance")


def test_the_flagged_files_carry_their_acl(monkeypatch):
    import app.shared.samba_auth as samba_auth

    asked = []

    def fake_samba(cmd, **_kwargs):
        if cmd[0] == "smbcacls":
            assert cmd == ["smbcacls", "//filer01/S", cmd[2]]  # smbcacls knows no --port
            asked.append(cmd[2])
            return SimpleNamespace(returncode=0, stdout=CACLS.encode(), stderr=b"")
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    monkeypatch.setattr(sens, "run_samba", fake_samba)
    monkeypatch.setattr(samba_auth, "stream_samba", FakeStream(LS))
    ok, _message, details = sens.scan_smb_sensitivity({"host": "filer01", "share": "S", "path": "Finance", "username": "u", "password": "p",
                                                       "rules_version": sens.RULES_VERSION, "since": "2099-01-01T00:00:00+00:00",
                                                       "known_paths": ["Finance\\IT\\web.config"]})
    result = details["sensitivity"]
    assert ok and asked and len(asked) == len(set(asked))
    assert result["acls"] == [{"path": "Finance\\IT\\web.config", "acl": sens.parse_cacls(CACLS)}]
    assert all(item["acl"]["broad"] for item in result["findings"])
    assert result["files_open_to_all"] == result["files_flagged"]
