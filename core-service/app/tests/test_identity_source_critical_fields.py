from __future__ import annotations

from types import SimpleNamespace

from app.api.identity_sources import changed_critical_fields

SOURCE = SimpleNamespace(host="dc01.example.test", base_dn="DC=example,DC=test", protocol="ldap", port=389)


def test_fields_sent_again_unchanged_are_not_changes() -> None:
    updates = {"host": "DC01.example.test ", "base_dn": "dc=example,dc=test", "name": "Renamed"}
    assert changed_critical_fields(SOURCE, updates) == []


def test_switching_to_ldaps_is_allowed() -> None:
    assert changed_critical_fields(SOURCE, {"protocol": "ldaps", "port": 636}) == []


def test_another_server_or_base_dn_is_a_change() -> None:
    assert changed_critical_fields(SOURCE, {"host": "dc02.example.test", "base_dn": "DC=other,DC=test"}) == ["base_dn", "host"]
