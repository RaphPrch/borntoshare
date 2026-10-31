from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api import access_requests as routes
from app.api import advanced_settings
from app.services.authorization import ActorContext, is_own_request


class _Db:
    """Answers `is_own_request` and the permission change from one request row."""

    def __init__(self, *, requester=5, principal=None, binding=False, status="pending", permission="write") -> None:
        self.row = {"status": status, "requester_identity_id": requester, "requested_principal_json": json.dumps(principal or {})}
        self.binding = binding
        self.items = [{"id": 1, "target_id": 77, "permission": permission}]
        self.update = None
        self._result = None

    def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        if sql.startswith("UPDATE access_request_items"):
            self.update = dict(params)
        self._result = self.items
        return self

    def mappings(self):
        return self

    def first(self):
        return self.row

    def all(self):
        return self._result

    def commit(self) -> None:
        pass


class _BindingDb(_Db):
    def execute(self, statement, params=None):
        self.is_binding_query = "FROM identities i" in str(statement)
        return super().execute(statement, params)

    def first(self):
        if self.is_binding_query:
            return (1,) if self.binding else None
        return self.row


def _request(identity: int, roles: str = "user") -> Request:
    return Request(
        {
            "type": "http",
            "headers": [
                (b"x-identity-id", str(identity).encode()),
                (b"x-roles", roles.encode()),
                (b"x-actor-display", b"Actor"),
            ],
        }
    )


def _actor(identity: int) -> ActorContext:
    return ActorContext(identity_id=identity, roles=frozenset({"user"}))


def test_own_request_covers_the_requester_and_the_beneficiary() -> None:
    assert is_own_request(_BindingDb(requester=5), _actor(5), 1) is True
    assert is_own_request(_BindingDb(requester=6, principal={"identity_id": 5}), _actor(5), 1) is True
    assert is_own_request(_BindingDb(requester=6, principal={"dn": "CN=me"}, binding=True), _actor(5), 1) is True
    assert is_own_request(_BindingDb(requester=6, principal={"dn": "CN=other"}), _actor(5), 1) is False


def test_guardian_cannot_approve_their_own_request_and_the_attempt_is_logged(monkeypatch) -> None:
    logged: list[dict] = []
    monkeypatch.setattr(routes, "log_activity", lambda db, **kwargs: logged.append(kwargs))
    monkeypatch.setattr(routes, "_request_event_labels", lambda db, req_id: {})

    with pytest.raises(HTTPException) as refused:
        routes.ensure_requests_approvable([1], _request(5), db=_BindingDb(requester=5))

    assert refused.value.status_code == 403
    assert refused.value.detail["code"] == "SELF_APPROVAL_FORBIDDEN"
    assert logged[0]["action"] == "access_request.approve" and logged[0]["outcome"] == "denied"


def test_administrator_is_not_blocked_on_their_own_request(monkeypatch) -> None:
    monkeypatch.setattr(routes, "log_activity", lambda db, **kwargs: pytest.fail("nothing to log here"))
    routes.ensure_requests_approvable([1], _request(5, "platform_admin"), db=_BindingDb(requester=5))


def _change(monkeypatch, db, *, held="NONE", identity=5, in_progress=False):
    logged: list[dict] = []
    monkeypatch.setattr(routes, "log_activity", lambda db, **kwargs: logged.append(kwargs))
    monkeypatch.setattr(routes, "_request_event_labels", lambda db, req_id: {"storage_root": "Finance"})
    monkeypatch.setattr(routes, "_current_access_level_for_principal", lambda **kwargs: held)
    monkeypatch.setattr(routes, "approvals_in_progress", {1} if in_progress else set())
    payload = routes.ChangePermissionPayload(permission="read", reason="Lecture suffit")
    try:
        return routes.change_access_request_permission(1, payload, _request(identity), db), logged
    except HTTPException as exc:
        return exc, logged


def test_changing_the_level_keeps_the_original_and_is_logged(monkeypatch) -> None:
    db = _Db()
    out, logged = _change(monkeypatch, db)
    assert not isinstance(out, HTTPException)
    assert db.update["permission"] == "read" and db.update["reason"] == "Lecture suffit"
    assert logged[0]["action"] == "access_request.permission_changed" and logged[0]["outcome"] == "success"
    assert logged[0]["context_json"]["from"] == "WRITE" and logged[0]["context_json"]["to"] == "READ"


@pytest.mark.parametrize(
    "db_args,held,in_progress,code",
    [
        ({"status": "approved"}, "NONE", False, "ACCESS_REQUEST_ALREADY_DECIDED"),
        ({"permission": "read"}, "NONE", False, "PERMISSION_UNCHANGED"),
        ({}, "READ", False, "ACCESS_ALREADY_GRANTED"),
        ({}, "NONE", True, "APPROVAL_IN_PROGRESS"),
    ],
)
def test_refused_level_changes_write_nothing_and_are_logged(monkeypatch, db_args, held, in_progress, code) -> None:
    db = _Db(**db_args)
    out, logged = _change(monkeypatch, db, held=held, in_progress=in_progress)
    assert isinstance(out, HTTPException) and out.status_code == 409 and out.detail["code"] == code
    assert db.update is None
    assert logged[0]["outcome"] == "denied"


def test_min_guardians_setting_falls_back_on_an_invalid_value(monkeypatch) -> None:
    monkeypatch.setattr(advanced_settings, "_read_payload", lambda db: {"governance": {"minGuardians": 3}})
    assert advanced_settings.min_guardians(SimpleNamespace()) == 3
    monkeypatch.setattr(advanced_settings, "_read_payload", lambda db: {"governance": {"minGuardians": 0}})
    assert advanced_settings.min_guardians(SimpleNamespace()) == 2


def test_saving_an_invalid_minimum_is_refused(monkeypatch) -> None:
    monkeypatch.setattr(advanced_settings, "_read_payload", lambda db: {"logging": {"level": "INFO"}, "governance": {"minGuardians": 2}})
    monkeypatch.setattr(advanced_settings, "_write_payload", lambda db, payload: pytest.fail("must not save"))
    with pytest.raises(HTTPException) as refused:
        advanced_settings.save_advanced_config({"governance": {"minGuardians": 0}}, _request(1, "platform_admin"), db=SimpleNamespace())
    assert refused.value.detail["code"] == "MIN_GUARDIANS_INVALID"
