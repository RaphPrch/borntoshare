from __future__ import annotations

import sys

import pytest
from fastapi import HTTPException

if sys.version_info < (3, 10):
    pytest.skip("Requires Python >= 3.10 for SQLAlchemy mapped union annotations", allow_module_level=True)

from app.routers import internal_identities as router


class _FakeDB:
    def execute(self, *_args, **_kwargs):
        return _FakeRows([])


class _FakeRows:
    def __init__(self, rows):
        self._rows = list(rows)

    def mappings(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None


class _CaptureDB:
    def __init__(self, select_rows):
        self.calls = []
        self._select_rows = list(select_rows)
        self.commit_called = False

    def execute(self, statement, params=None):
        sql = str(statement)
        self.calls.append((sql, params))
        normalized = " ".join(sql.split()).lower()
        if normalized.startswith("select"):
            rows = self._select_rows.pop(0) if self._select_rows else []
            return _FakeRows(rows)
        return _FakeRows([])

    def commit(self):
        self.commit_called = True


def test_resolve_ad_identity_no_candidate_returns_no_candidate() -> None:
    payload = router.ResolveAdIdentityRequest(
        external_id=None,
        username=None,
        email=None,
    )

    out = router.resolve_ad_identity(payload, db=_FakeDB())
    assert out.found is False
    assert out.reason_code == "NO_CANDIDATE"


def test_resolve_ad_identity_batch_aggregates_results(monkeypatch) -> None:
    calls: list[router.ResolveAdIdentityRequest] = []

    def _fake_resolve(payload: router.ResolveAdIdentityRequest, db):
        _ = db
        calls.append(payload)
        if str(payload.external_id or "").lower().endswith("alice"):
            return router.ResolveAdIdentityResponse(
                found=True,
                reason_code="FOUND_EXISTING",
                identity_id="10",
                username="alice",
                external_id=str(payload.external_id),
            )
        return router.ResolveAdIdentityResponse(
            found=False,
            reason_code="NOT_FOUND",
        )

    monkeypatch.setattr(router, "resolve_ad_identity", _fake_resolve)

    out = router.resolve_ad_identity_batch(
        router.ResolveAdIdentityBatchRequest(
            identity_source_id=9,
            create_if_missing=True,
            items=[
                router.ResolveAdIdentityRequest(external_id="alice"),
                router.ResolveAdIdentityRequest(external_id="ghost"),
            ],
        ),
        db=_FakeDB(),
    )

    assert out.count == 2
    assert out.found == 1
    assert out.not_found == 1
    assert out.items[0].index == 0
    assert out.items[0].found is True
    assert out.items[0].reason_code == "FOUND_EXISTING"
    assert out.items[1].index == 1
    assert out.items[1].found is False
    assert out.items[1].reason_code == "NOT_FOUND"
    assert len(calls) == 2
    assert calls[0].identity_source_id == 9
    assert calls[0].create_if_missing is True


def test_resolve_ad_identity_create_if_missing_creates_from_snapshot_user() -> None:
    db = _CaptureDB(
        [
            [],
            [],
            [{
                "external_id": "CN=Alice,OU=Users,DC=example,DC=com",
                "username": "alice",
                "display_name": "Alice",
                "email": "alice@example.com",
                "is_active": 1,
            }],
            [{
                "id": 42,
                "username": "alice",
                "display_name": "Alice",
                "email": "alice@example.com",
                "external_id": "CN=Alice,OU=Users,DC=example,DC=com",
                "is_active": 1,
            }],
        ]
    )

    out = router.resolve_ad_identity(
        router.ResolveAdIdentityRequest(
            external_id="CN=Alice,OU=Users,DC=example,DC=com",
            identity_source_id=9,
            create_if_missing=True,
        ),
        db=db,
    )

    assert out.found is True
    assert out.reason_code == "CREATED_FROM_SNAPSHOT"
    assert out.identity_id == "42"
    assert db.commit_called is True
    assert any("insert into identities" in " ".join(sql.split()).lower() for sql, _ in db.calls)


def test_resolve_login_identity_no_candidate_returns_no_candidate() -> None:
    out = router.resolve_login_identity(
        router.ResolveLoginIdentityRequest(login=None, username=None, upn_hint=None),
        db=_FakeDB(),
    )

    assert out.found is False
    assert out.reason_code == "NO_CANDIDATE"


def test_resolve_login_identity_returns_identity_payload() -> None:
    db = _FakeDB()
    db.execute = lambda *_args, **_kwargs: _FakeRows([{
        "id": 22,
        "username": "b2s",
        "display_name": "b2s",
        "email": None,
        "auth_source": "ad",
        "source_id": 2,
        "external_id": "guid-1",
        "is_active": 1,
        "status": "active",
        "type": "user",
        "provisioning_source": "explicit",
    }])

    out = router.resolve_login_identity(
        router.ResolveLoginIdentityRequest(login="b2s", username="b2s", upn_hint=None),
        db=db,
    )

    assert out.found is True
    assert out.identity_id == "22"
    assert out.auth_source == "ad"
    assert out.source_id == 2
    assert out.provisioning_source == "explicit"
