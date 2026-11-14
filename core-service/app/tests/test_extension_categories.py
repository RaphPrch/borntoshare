"""Audit events routed by family (sign-ins, requests, identities, folders…) and, if chosen, the failures only."""
from __future__ import annotations

from app.services import extensions as ext


def _audit(action: str, outcome: str = "success") -> dict:
    return ext.event_from_activity({"action": action, "outcome": outcome, "actor_display": "admin", "target_display": "DATA"})


def test_each_action_has_its_family() -> None:
    assert _audit("auth.login")["category"] == "auth"
    assert _audit("access_request.created")["category"] == "access"
    assert _audit("identity.password_changed")["category"] == "identities"
    assert _audit("storage_root.created")["category"] == "folders"
    assert _audit("advanced_settings.setup_completed")["category"] == "settings"
    assert _audit("something.new")["category"] == "other"


def test_all_the_audit_by_default() -> None:
    assert ext.wanted(dict(ext.DEFAULT_ROUTES), _audit("tag.created"))


def test_only_the_families_chosen() -> None:
    routes = {**ext.DEFAULT_ROUTES, "categories": ["auth", "folders"]}
    assert ext.wanted(routes, _audit("auth.login"))
    assert not ext.wanted(routes, _audit("tag.created"))


def test_failures_only() -> None:
    routes = {**ext.DEFAULT_ROUTES, "failures_only": True}
    assert ext.wanted(routes, _audit("auth.login", "failure"))
    assert not ext.wanted(routes, _audit("auth.login", "success"))


def test_the_family_travels_in_syslog_and_cef() -> None:
    event = _audit("auth.login", "failure")
    assert 'category="auth"' in ext.syslog_line(event, {"format": "rfc5424"})
    assert "cat=auth" in ext.syslog_line(event, {"format": "cef"})
