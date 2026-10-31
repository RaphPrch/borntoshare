from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api import identity_list as router


def _request(identity: int) -> Request:
    return Request({"type": "http", "headers": [(b"x-identity-id", str(identity).encode()), (b"x-actor-display", b"A")]})


@pytest.fixture
def logged(monkeypatch) -> list[dict]:
    rows: list[dict] = []
    monkeypatch.setattr(router, "log_activity", lambda db, **kwargs: rows.append(kwargs))
    return rows


def _refusal(request: Request, **kwargs) -> dict:
    with pytest.raises(HTTPException) as refused:
        router._refuse_admin_loss(None, request, action="identity.account_deleted", **kwargs)
    return refused.value.detail


def test_nobody_changes_their_own_account_and_it_is_logged(monkeypatch, logged) -> None:
    assert _refusal(_request(7), identity_id=7)["code"] == "IDENTITY_SELF_CHANGE_FORBIDDEN"
    assert logged[0]["outcome"] == "denied"


def test_the_last_administrator_stays(monkeypatch, logged) -> None:
    monkeypatch.setattr(router, "_subject_is_admin", lambda db, **kwargs: True)
    monkeypatch.setattr(router, "_other_admin_exists", lambda db, **kwargs: False)
    assert _refusal(_request(7), identity_id=8)["code"] == "LAST_ADMIN_FORBIDDEN"
    assert _refusal(_request(7), group_id=3)["code"] == "LAST_ADMIN_FORBIDDEN"


def test_an_administrator_can_go_when_another_remains(monkeypatch, logged) -> None:
    monkeypatch.setattr(router, "_subject_is_admin", lambda db, **kwargs: True)
    monkeypatch.setattr(router, "_other_admin_exists", lambda db, **kwargs: True)
    router._refuse_admin_loss(None, _request(7), action="identity.account_deleted", identity_id=8)
    assert logged == []


def test_a_person_without_the_role_is_not_concerned(monkeypatch, logged) -> None:
    monkeypatch.setattr(router, "_subject_is_admin", lambda db, **kwargs: False)
    router._refuse_admin_loss(None, _request(7), action="identity.account_deleted", identity_id=8)
    assert logged == []


def test_objects_outside_the_directory_are_refused() -> None:
    from types import SimpleNamespace

    source = SimpleNamespace(base_dn="DC=Example,DC=Test")
    router._refuse_outside_directory(source, "CN=Jane,OU=People,DC=example,DC=test")
    for dn in ("CN=Jane,DC=other,DC=test", None):
        with pytest.raises(HTTPException) as refused:
            router._refuse_outside_directory(source, dn)
        assert refused.value.detail["code"] == "OUTSIDE_DIRECTORY"
