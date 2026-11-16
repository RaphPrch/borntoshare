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


def test_a_silent_dns_does_not_hold_the_folders(monkeypatch) -> None:
    """A domain controller whose name does not answer: the call ends within the budget, the answer is kept."""
    import threading
    import time

    release = threading.Event()

    def lookup(host):
        if host == "dc.slow.invalid":
            release.wait(5)
            return "10.0.0.9"
        return "10.0.0.1"

    monkeypatch.setattr(domain_dns, "_lookup", lookup)
    monkeypatch.setattr(domain_dns, "_BUDGET_SECONDS", 0.2)
    monkeypatch.setattr(domain_dns, "_resolved", {})
    monkeypatch.setattr(domain_dns, "_pending", {})
    started = time.monotonic()
    assert domain_dns.resolve_hosts(["dc.fast.local", "dc.slow.invalid"]) == {"dc.fast.local": "10.0.0.1", "dc.slow.invalid": None}
    assert time.monotonic() - started < 1
    release.set()
    for _ in range(50):
        if "dc.slow.invalid" in domain_dns._resolved:
            break
        time.sleep(0.02)
    assert domain_dns.resolve_hosts(["dc.slow.invalid"]) == {"dc.slow.invalid": "10.0.0.9"}
