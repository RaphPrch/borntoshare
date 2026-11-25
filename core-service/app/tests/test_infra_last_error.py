"""A component back to normal keeps its last error (when, and why) in the health page."""
from __future__ import annotations

import json

from app.services import infrastructure_service as infra


class _Db:
    def __init__(self, stored):
        self.stored = stored  # component -> (status, details_json)
        self.written = {}

    def execute(self, statement, params=None):
        sql = str(statement)
        if sql.startswith("SELECT component, status, details_json"):
            rows = [(c, s, d) for c, (s, d) in self.stored.items()]
            return type("R", (), {"all": lambda self_: rows})()
        if "INSERT INTO infra_component_status" in sql:
            self.written[params["component"]] = (params["status"], params["details"])
        return None


def test_the_last_error_is_kept_once_the_component_is_back(monkeypatch) -> None:
    from app.services import notifications

    monkeypatch.setattr(notifications, "admin_alert", lambda *a, **k: None)
    db = _Db({"identity_source:2": ("healthy", None)})
    infra.record_components(db, [{"component": "identity_source:2", "status": "down", "message": "LDAPS: certificate expired"}], checked_by="test")
    status, details = db.written["identity_source:2"]
    assert status == "down" and json.loads(details)["last_error"] == "LDAPS: certificate expired"

    db = _Db({"identity_source:2": ("down", details)})
    infra.record_components(db, [{"component": "identity_source:2", "status": "healthy", "message": "bind ok", "details": {"version": 3}}], checked_by="test")
    status, back = db.written["identity_source:2"]
    back = json.loads(back)
    assert status == "healthy" and back["last_error"] == "LDAPS: certificate expired" and back["last_error_at"] and back["version"] == 3


def test_a_component_never_in_error_has_none() -> None:
    db = _Db({})
    infra.record_components(db, [{"component": "service:core", "status": "healthy", "message": "ok"}], checked_by="test")
    assert db.written["service:core"] == ("healthy", None)
