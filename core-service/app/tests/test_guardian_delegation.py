from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api import identity_list
from app.services import authorization


def _request(identity_id: int | None = 7, roles: str = "user") -> Request:
    headers = [(b"x-roles", roles.encode())]
    if identity_id is not None:
        headers.append((b"x-identity-id", str(identity_id).encode()))
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers, "query_string": b""})


class _Rows:
    def __init__(self, rows=None, first=None):
        self._rows = rows or []
        self._first = first

    def first(self):
        return self._first

    def mappings(self):
        return self

    def all(self):
        return self._rows


def test_a_guardian_sets_a_backup_for_himself_only(monkeypatch):
    seen = {}
    monkeypatch.setattr(identity_list, "_create_substitution", lambda db, request, identity_id, payload: seen.setdefault("guardian", identity_id) or 1)
    identity_list.create_my_substitute(_request(7), {"substitute_identity_id": 9}, db=object())
    # The guardian is the signed-in person, whatever the payload says
    assert seen["guardian"] == 7


def test_a_guardian_cannot_end_the_backup_of_another_guardian(monkeypatch):
    monkeypatch.setattr(identity_list.identity_list_sql, "revoke_substitute_1", lambda db, params: _Rows(first=(3,)))
    with pytest.raises(HTTPException) as refused:
        identity_list.revoke_my_substitute(11, _request(7), db=object())
    assert refused.value.status_code == 404


def test_only_a_guardian_searches_backup_candidates(monkeypatch):
    monkeypatch.setattr(identity_list.identity_list_sql, "create_substitute_2", lambda db, params: _Rows(first=None))
    with pytest.raises(HTTPException) as refused:
        identity_list.list_my_substitute_candidates(_request(7), q="dup", db=object())
    assert refused.value.status_code == 403


def test_the_backup_routes_need_a_signed_in_person():
    with pytest.raises(HTTPException) as refused:
        identity_list.list_my_substitutes(_request(None), db=object())
    assert refused.value.status_code == 401


class _Db:
    """First query: is the person a guardian of the folder; second: the guardians they replace."""

    def __init__(self, guardian: bool, replaced: list[str]):
        self.guardian, self.replaced = guardian, replaced

    def execute(self, statement, params=None):
        if "LIMIT 1" in str(statement):
            return _Rows(first=(1,) if self.guardian else None)
        return _Rows(rows=[(name,) for name in self.replaced])


def test_a_decision_by_a_backup_names_the_guardians_replaced():
    actor = authorization.actor_from_request(_request(7))
    assert authorization.replaced_guardians(_Db(False, ["Alice Martin"]), actor, 4) == ["Alice Martin"]
    # A guardian of the folder decides for themselves
    assert authorization.replaced_guardians(_Db(True, ["Alice Martin"]), actor, 4) == []
