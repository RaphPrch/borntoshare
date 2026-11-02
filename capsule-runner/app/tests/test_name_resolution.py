from __future__ import annotations

from app.shared import name_resolution as nr
from app.shared import samba_auth

DNS = [{"domain": "corp.local", "servers": ["10.0.0.1"]}]


def _answers(monkeypatch, table):
    monkeypatch.setattr(nr, "query_a", lambda name, server, timeout=3.0: table.get(name.lower()))
    monkeypatch.setattr(nr, "_load", lambda: DNS)


def test_short_and_full_names_of_the_domain_use_its_dns(monkeypatch):
    _answers(monkeypatch, {"filer01.corp.local": "10.0.0.5"})
    assert nr.domain_resolve("FILER01") == ("10.0.0.5", "FILER01.corp.local", "10.0.0.1")
    assert nr.domain_resolve("filer01.corp.local")[0] == "10.0.0.5"
    assert nr.domain_resolve("www.example.org") is None
    assert nr.domain_resolve("10.0.0.9") is None


def test_a_domain_proposed_by_a_directory_comes_after_the_usual_resolver(monkeypatch):
    proposed = [{"domain": "example.test", "servers": ["10.0.0.2"], "fallback": True}]
    monkeypatch.setattr(nr, "query_a", lambda name, server, timeout=3.0: "10.9.9.9")
    monkeypatch.setattr(nr, "_system", lambda name: "10.0.0.7" if name == "dc.example.test" else None)
    assert nr.domain_resolve("dc.example.test", proposed) is None  # the usual resolver knows it: unchanged
    monkeypatch.setattr(nr, "_system", lambda name: "10.0.0.7" if name == "DC.example.test" else None)
    assert nr.domain_resolve("DC", proposed) == ("10.0.0.7", "DC.example.test", "system")
    assert nr.domain_resolve("other.example.test", proposed) == ("10.9.9.9", "other.example.test", "10.0.0.2")


def test_samba_targets_are_given_by_address(monkeypatch):
    _answers(monkeypatch, {"filer01.corp.local": "10.0.0.5"})
    cmd = samba_auth._with_domain_addresses(["smbcacls", "//FILER01/Share", "Dir", "-c", "exit"])
    assert cmd == ["smbcacls", "//10.0.0.5/Share", "Dir", "-c", "exit"]
    assert samba_auth._with_domain_addresses(["smbclient", "-L", "FILER01"])[2] == "10.0.0.5"
    assert samba_auth._with_domain_addresses(["rpcclient", "FILER01", "-c", "x"])[1] == "10.0.0.5"
    assert samba_auth._with_domain_addresses(["smbclient", "//unknown.example/s"])[1] == "//unknown.example/s"


def test_a_dns_answer_is_decoded():
    import struct

    question = b"\x07filer01\x04corp\x05local\x00"
    answer = b"\xc0\x0c" + struct.pack(">HHIH", 1, 1, 60, 4) + bytes([10, 0, 0, 5])
    class _Sock:
        def __init__(self, *a): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def settimeout(self, t): pass
        def sendto(self, packet, addr): self.ident = packet[:2]
        def recv(self, n): return self.ident + struct.pack(">HHHHH", 0x8180, 1, 1, 0, 0) + question + struct.pack(">HH", 1, 1) + answer

    original = nr.socket.socket
    nr.socket.socket = _Sock
    try:
        assert nr.query_a("filer01.corp.local", "10.0.0.1") == "10.0.0.5"
    finally:
        nr.socket.socket = original
