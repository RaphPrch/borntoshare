from __future__ import annotations

from app.services import domain_dns


def test_valid_settings_are_accepted() -> None:
    assert domain_dns.validate_entries([{"domain": "corp.local", "servers": ["172.20.3.86"]}]) is None
    assert domain_dns.validate_entries([]) is None


def test_invalid_settings_are_refused() -> None:
    assert domain_dns.validate_entries([{"domain": "corp.local", "servers": ["dc01.corp.local"]}])
    assert domain_dns.validate_entries([{"domain": "not a domain", "servers": ["10.0.0.1"]}])
    assert domain_dns.validate_entries([{"domain": "corp.local", "servers": []}])
    assert domain_dns.validate_entries([{"domain": "corp.local", "servers": ["10.0.0.1"]}] * 2)


def test_a_short_name_is_found_in_the_domain(monkeypatch) -> None:
    monkeypatch.setattr(domain_dns, "query_a", lambda name, server, timeout=2.0: "10.0.0.5" if name == "FILER01.corp.local" else None)
    dns = [{"domain": "corp.local", "servers": ["10.0.0.1"]}]
    assert domain_dns.addresses("FILER01", dns) == {"10.0.0.5"}
    assert domain_dns.addresses("10.0.0.7", dns) == {"10.0.0.7"}


def test_directory_domains_are_only_a_fallback(monkeypatch) -> None:
    monkeypatch.setattr(domain_dns, "configured", lambda db: [{"domain": "corp.local", "servers": ["10.0.0.1"]}])
    monkeypatch.setattr(domain_dns, "proposed", lambda db: [
        {"domain": "corp.local", "servers": ["10.0.0.9"], "source": "AD"},
        {"domain": "example.test", "servers": ["10.0.0.2"], "source": "Lab"},
    ])
    entries = domain_dns.effective(None)
    assert [(e["domain"], e["servers"], bool(e.get("fallback"))) for e in entries] == [
        ("corp.local", ["10.0.0.1"], False),
        ("example.test", ["10.0.0.2"], True),
    ]
