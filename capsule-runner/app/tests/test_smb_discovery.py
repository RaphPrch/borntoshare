from __future__ import annotations

from app.actions import smb_discovery as action

NEGOTIATION = """
 negotiated dialect[SMB3_11] against server[172.20.12.195]
                        AvNbComputerName         : 'FILER01'
                        AvDnsDomainName          : 'CORP.LOCAL'
                        AvDnsComputerName        : 'FILER01.corp.local'
session setup failed: NT_STATUS_NOT_SUPPORTED
"""


def test_the_negotiation_gives_version_names_and_domain():
    assert action.describe_negotiation(NEGOTIATION) == {
        "dialect": "SMB 3.1.1",
        "netbios_name": "FILER01",
        "dns_name": "FILER01.corp.local",
        "domain": "corp.local",
    }


def test_nothing_read_stays_empty():
    assert action.describe_negotiation("") == {"dialect": None, "netbios_name": None, "dns_name": None, "domain": None}


def test_a_closed_port_is_a_clear_failure(monkeypatch):
    monkeypatch.setattr("app.shared.name_resolution.resolve", lambda host: "10.0.0.1")

    def refuse(*_a, **_k):
        raise OSError("refused")

    monkeypatch.setattr(action.socket, "create_connection", refuse)
    ok, _message, details = action.discover_smb_server({"host": "fs.example.test"})
    assert not ok and details["failure_code"] == "SMB_DISCOVERY_PORT_CLOSED"
