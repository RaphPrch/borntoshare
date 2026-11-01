from __future__ import annotations

from app.actions import directory_discovery as action


def test_active_directory_is_recognised_with_its_default_base():
    described = action.describe_root({
        "supportedCapabilities": ["1.2.840.113556.1.4.800"],
        "defaultNamingContext": "DC=example,DC=test",
        "namingContexts": ["CN=Configuration,DC=example,DC=test", "DC=example,DC=test"],
    })
    assert described == {"flavor": "ad", "base_dn": "DC=example,DC=test"}


def test_openldap_base_skips_technical_contexts():
    described = action.describe_root({"namingContexts": ["cn=config", "dc=example,dc=org"]})
    assert described == {"flavor": "openldap", "base_dn": "dc=example,dc=org"}


def test_ldaps_with_unreadable_root_still_gives_the_certificate(monkeypatch):
    monkeypatch.setattr(action, "fetch_tls_certificate", lambda _p: (True, "ok", {"sha256": "aa"}))
    monkeypatch.setattr(action, "_read_root", lambda *_a: None)
    ok, _message, details = action.discover_directory({"host": "dc.example.test"})
    assert ok and details["protocol"] == "ldaps" and details["port"] == 636
    assert details["certificate"] == {"sha256": "aa"} and details["base_dn"] is None


def test_falls_back_to_plain_ldap(monkeypatch):
    monkeypatch.setattr(action, "fetch_tls_certificate", lambda _p: (False, "no", {}))
    monkeypatch.setattr(action, "_read_root", lambda *_a: {"namingContexts": ["dc=example,dc=org"]})
    ok, _message, details = action.discover_directory({"host": "ldap.example.test"})
    assert ok and details["protocol"] == "ldap" and details["port"] == 389 and details["certificate"] is None


def test_silent_server_is_a_clear_failure(monkeypatch):
    monkeypatch.setattr(action, "fetch_tls_certificate", lambda _p: (False, "no", {}))
    monkeypatch.setattr(action, "_read_root", lambda *_a: None)
    ok, _message, details = action.discover_directory({"host": "nothing.example.test"})
    assert not ok and details["failure_code"] == "DISCOVERY_UNREACHABLE"
