"""FSRM quotas over WinRM: the script, the result, the Kerberos realm and server name (WinRM itself is mocked)."""
from __future__ import annotations

import json

import pytest

from app.actions import quota
from app.shared import winrm


def _params(**extra):
    return {"host": "10.0.0.5", "share": "Angers", "path": "Finance", "username": "CORP\\svc", "password": "x", "domain": "corp.local", **extra}


def test_parameters_travel_as_json_in_a_single_quoted_here_string() -> None:
    script = quota.build_script({"op": "set", "share": "A'B", "path": "x\\y", "limit_bytes": 1048576})
    block = script.split("$p = @'\n", 1)[1].split("\n'@", 1)[0]
    assert json.loads(block) == {"op": "set", "share": "A'B", "path": "x\\y", "limit_bytes": 1048576}


def test_set_sends_the_limit_and_returns_the_quota_read_back(monkeypatch) -> None:
    seen = {}

    def fake_run(**kwargs):
        seen.update(kwargs)
        return {"output": '{"local_path":"D:\\\\Shares\\\\Angers\\\\Finance","exists":true,"limit_bytes":10737418240,"used_bytes":5,"thresholds":[85]}', "errors": []}

    monkeypatch.setattr(quota, "run_powershell", fake_run)
    ok, message, details = quota.folder_quota(_params(operation="set", limit_bytes=10 * 1024 ** 3, warn_percent=85))
    assert ok, message
    assert details["quota"]["limit_bytes"] == 10737418240
    sent = json.loads(seen["script"].split("$p = @'\n", 1)[1].split("\n'@", 1)[0])
    assert sent["op"] == "set" and sent["limit_bytes"] == 10 * 1024 ** 3 and sent["soft"] is False


@pytest.mark.parametrize("extra,code", [
    ({"operation": "set", "limit_bytes": 10}, "QUOTA_LIMIT_INVALID"),
    ({"operation": "set", "limit_bytes": 1024 ** 3, "warn_percent": 20}, "QUOTA_THRESHOLD_INVALID"),
    ({"operation": "wipe"}, "QUOTA_OPERATION_INVALID"),
])
def test_invalid_requests_never_reach_the_server(monkeypatch, extra, code) -> None:
    monkeypatch.setattr(quota, "run_powershell", lambda **_: pytest.fail("no call expected"))
    ok, _message, details = quota.folder_quota(_params(**extra))
    assert not ok and details["failure_code"] == code


def test_a_server_without_fsrm_says_how_to_install_it(monkeypatch) -> None:
    monkeypatch.setattr(quota, "run_powershell", lambda **_: {"output": '{"error":"FSRM_NOT_INSTALLED","message":"not installed"}', "errors": []})
    ok, _message, details = quota.folder_quota(_params())
    assert not ok and details["failure_code"] == "FSRM_NOT_INSTALLED" and "Install-WindowsFeature" in details["hint"]


def test_winrm_errors_keep_their_code_and_hint(monkeypatch) -> None:
    def boom(**_):
        raise winrm.WinRMError("WINRM_KERBEROS_FAILED", "Kerberos refused the account", hint="Check the account")

    monkeypatch.setattr(quota, "run_powershell", boom)
    ok, _message, details = quota.folder_quota(_params())
    assert not ok and details["failure_code"] == "WINRM_KERBEROS_FAILED" and details["hint"] == "Check the account"


def test_apply_refuses_a_plain_read() -> None:
    ok, _message, details = quota.apply_folder_quota(_params(operation="read"))
    assert not ok and details["failure_code"] == "QUOTA_OPERATION_INVALID"


def test_realm_from_upn_netbios_or_domain(monkeypatch) -> None:
    monkeypatch.setattr(winrm.name_resolution, "_load", lambda: [{"domain": "corp.local", "servers": ["10.0.0.1"]}])
    assert winrm.realm_of("svc@corp.local") == "CORP.LOCAL"
    assert winrm.realm_of("CORP\\svc") == "CORP.LOCAL"
    assert winrm.realm_of("svc", "corp.local") == "CORP.LOCAL"
    assert winrm.principal_of("CORP\\svc", "CORP.LOCAL") == "svc@CORP.LOCAL"
    with pytest.raises(winrm.WinRMError):
        winrm.realm_of("OTHER\\svc")


def test_server_name_of_an_ip_comes_from_its_name_checked_in_the_domain_dns(monkeypatch) -> None:
    monkeypatch.setattr(winrm.name_resolution, "domain_resolve", lambda name: ("10.0.0.5", name, "10.0.0.1") if name == "filer01.corp.local" else None)
    assert winrm.server_fqdn("10.0.0.5", "filer01", "CORP.LOCAL") == "filer01.corp.local"
    assert winrm.server_fqdn("filer02", None, "CORP.LOCAL") == "filer02.corp.local"
    with pytest.raises(winrm.WinRMError) as refused:
        winrm.server_fqdn("10.0.0.9", "filer01.corp.local", "CORP.LOCAL")
    assert refused.value.code == "WINRM_SERVER_NAME_MISMATCH"
    with pytest.raises(winrm.WinRMError):
        winrm.server_fqdn("10.0.0.9", "File server Angers", "CORP.LOCAL")
    # The DNS does not answer: the name is used as declared, Kerberos checks it
    assert winrm.server_fqdn("10.0.0.9", "filer09", "CORP.LOCAL") == "filer09.corp.local"


def test_password_keywords_are_found_by_name_and_content() -> None:
    from app.actions import sensitivity

    names = ["Codes d'accès wifi.xlsx", "comptes admin.docx", "KeePass export.csv", "Passwort Liste.txt", "budget 2026.xlsx"]
    flagged = [name for name in names if sensitivity.name_findings(name)]
    assert flagged == names[:4]
    text = "$p = ConvertTo-SecureString 'Hiver2026!' -AsPlainText -Force\nnet use \\\\srv\\share S3cret! /user:CORP\\bob\n"
    for line in ("net use P: \\\\FILER01\\Lyon PartageLyon2026 /user:CORP\\svc /persistent:yes", "net user bob Bob2026x! /add"):
        assert sensitivity.content_findings("x.bat", line), line
    rules = {item["rule"] for item in sensitivity.content_findings("deploy.ps1", text)}
    assert "Password written in a script" in rules and "Password on a net use / net user command" in rules


def test_a_quota_driver_not_yet_attached_says_to_restart(monkeypatch) -> None:
    monkeypatch.setattr(quota, "run_powershell", lambda **_: {"output": '{"error":"FSRM_REFUSED","message":"Non trouvé "}', "errors": []})
    ok, _message, details = quota.folder_quota(_params(operation="set", limit_bytes=1024 ** 3))
    assert not ok and "Restart" in details["hint"]
