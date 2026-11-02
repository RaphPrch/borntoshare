from __future__ import annotations

import base64

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import internal_secrets
from app.services import secret_store

REF = "sm://storage-endpoint/smb/a"


class _Db:
    """secret_items in memory."""

    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}
        self.used: set[str] = set()
        self._row = None

    def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        self.last_sql = sql
        if sql.startswith("DELETE"):
            return self
        if sql.startswith("SELECT NOT EXISTS"):
            self._used = params["ref"] in self.used
            return self
        if sql.startswith("INSERT"):
            self.rows[params["ref"]] = {"iv": params["iv"], "ciphertext": params["ciphertext"]}
        self._row = self.rows.get(params["ref"])
        return self

    def scalar(self):
        return not self._used

    def mappings(self):
        return self

    def first(self):
        return self._row

    def commit(self) -> None:
        pass


@pytest.fixture(autouse=True)
def _key(monkeypatch) -> None:
    monkeypatch.setenv("B2S_SECRET_MASTER_KEY", base64.b64encode(b"0123456789abcdef0123456789abcdef").decode())


def test_a_stored_value_is_encrypted_and_read_back() -> None:
    db = _Db()
    ref = secret_store.store(db, "storage-endpoint/smb/a", "le-secret")
    assert ref == REF
    assert "le-secret" not in str(db.rows)
    assert secret_store.resolve(db, ref) == "le-secret"
    assert secret_store.exists(db, ref) is True


def test_a_password_in_use_is_never_overwritten() -> None:
    db = _Db()
    first = secret_store.store_unshared(db, "identity-sources/host/bind-password", "le-bon")
    assert first == "sm://identity-sources/host/bind-password"
    assert secret_store.store_unshared(db, "identity-sources/host/bind-password", "retest") == first
    db.used.add(first)
    other = secret_store.store_unshared(db, "identity-sources/host/bind-password", "autre")
    assert other != first and other.startswith(first + "-")
    assert secret_store.resolve(db, first) == "retest" and secret_store.resolve(db, other) == "autre"


@pytest.mark.parametrize("bad", ["sm://", "sm://../etc/passwd", "/etc/passwd"])
def test_invalid_references_are_refused(bad) -> None:
    with pytest.raises(secret_store.SecretInvalidRef):
        secret_store.resolve(_Db(), bad)


def test_a_missing_secret_is_not_found() -> None:
    with pytest.raises(secret_store.SecretNotFound):
        secret_store.resolve(_Db(), REF)


def test_a_value_copied_to_another_reference_cannot_be_decrypted() -> None:
    db = _Db()
    secret_store.store(db, "other/secret", "le-secret")
    db.rows[REF] = db.rows["sm://other/secret"]
    with pytest.raises(secret_store.SecretDecryptFailed):
        secret_store.resolve(db, REF)


def test_another_key_cannot_decrypt(monkeypatch) -> None:
    db = _Db()
    secret_store.store(db, REF, "le-secret")
    monkeypatch.setenv("B2S_SECRET_MASTER_KEY", base64.b64encode(b"f" * 32).decode())
    with pytest.raises(secret_store.SecretDecryptFailed):
        secret_store.resolve(db, REF)


def _client() -> tuple[FastAPI, TestClient]:
    app = FastAPI()
    app.include_router(internal_secrets.router)
    db = _Db()
    app.dependency_overrides[internal_secrets.get_db] = lambda: db
    return app, TestClient(app)


def test_the_routes_require_the_internal_token() -> None:
    _app, client = _client()
    assert client.post("/internal/secrets/resolve", json={"ref": REF}).status_code in {401, 403}
    assert client.post("/internal/secrets/store", json={"name": "a/b", "value": "v"}).status_code in {401, 403}


def test_the_routes_store_and_explain_a_missing_secret() -> None:
    app, client = _client()
    app.dependency_overrides[internal_secrets.require_internal_token] = lambda: None
    stored = client.post("/internal/secrets/store", json={"name": "a/b", "value": "v"})
    assert stored.json()["data"]["ref"] == "sm://a/b"
    assert client.post("/internal/secrets/resolve", json={"ref": "sm://a/b"}).json()["data"]["value"] == "v"
    missing = client.post("/internal/secrets/resolve", json={"ref": REF})
    assert missing.status_code == 404 and missing.json()["detail"]["code"] == "SECRET_NOT_FOUND"
