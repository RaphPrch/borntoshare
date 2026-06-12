from __future__ import annotations

from fastapi import HTTPException

from app.routers import internal_auth_local as module


class _Result:
    def __init__(self, row):
        self._row = row

    def mappings(self):
        return self

    def first(self):
        return self._row


class _FakeDB:
    def __init__(self, row):
        self._row = row
        self.update_params: dict | None = None
        self.commit_calls = 0

    def execute(self, statement, params=None):
        sql = str(statement).lower()
        if "update local_credentials" in sql:
            self.update_params = dict(params or {})
            return _Result(None)
        return _Result(self._row)

    def commit(self):
        self.commit_calls += 1


class _FakeRequest:
    headers: dict[str, str] = {}


def test_verify_local_credentials_success(monkeypatch) -> None:
    row = {
        "identity_id": 42,
        "username": "admin",
        "display_name": "Admin User",
        "email": "admin@corp.local",
        "is_active": 1,
        "auth_source": "local",
        "password_hash": "b2s$v=1$bcrypt$dummy",
    }
    db = _FakeDB(row)
    monkeypatch.setattr(module, "_verify_b2s_password", lambda *_a, **_k: True)

    out = module.verify_local_credentials(
        module.LocalVerifyPayload(username="admin", password="secret"),
        db=db,
    )

    assert out["identity_id"] == "42"
    assert out["username"] == "admin"
    assert "is_admin" not in out


def test_verify_local_credentials_rejects_invalid_password(monkeypatch) -> None:
    row = {
        "identity_id": 42,
        "username": "admin",
        "is_active": 1,
        "auth_source": "local",
        "password_hash": "b2s$v=1$bcrypt$dummy",
    }
    db = _FakeDB(row)
    monkeypatch.setattr(module, "_verify_b2s_password", lambda *_a, **_k: False)

    try:
        module.verify_local_credentials(
            module.LocalVerifyPayload(username="admin", password="wrong"),
            db=db,
        )
        assert False, "Expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 401


def test_change_local_password_updates_hash_and_commits(monkeypatch) -> None:
    row = {
        "identity_id": 77,
        "is_active": 1,
        "auth_source": "local",
        "password_hash": "b2s$v=1$bcrypt$old",
    }
    db = _FakeDB(row)
    monkeypatch.setattr(module, "_verify_b2s_password", lambda *_a, **_k: True)
    monkeypatch.setattr(module, "_hash_b2s_password", lambda _pwd: "b2s$v=1$bcrypt$new")

    out = module.change_local_password(
        module.LocalChangePasswordPayload(
            username="admin",
            current_password="old_secret",
            new_password="new_secret",
        ),
        request=_FakeRequest(),
        db=db,
    )

    assert out["ok"] is True
    assert db.commit_calls == 1
    assert isinstance(db.update_params, dict)
    assert db.update_params["identity_id"] == 77
    assert db.update_params["password_hash"] == "b2s$v=1$bcrypt$new"
