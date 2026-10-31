from __future__ import annotations

import base64
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _build_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("INTERNAL_TOKEN", "itok")
    monkeypatch.setenv("B2S_SECRET_ALLOWED_PREFIXES", "sm://")
    monkeypatch.setenv("B2S_SECRET_ALLOW_ENV_PROVIDER", "false")
    monkeypatch.setenv("B2S_SECRET_ALLOW_WRITE", "true")
    monkeypatch.setenv("B2S_SECRET_WRITE_TOKEN", "wtok")
    monkeypatch.setenv("B2S_SECRET_MASTER_KEY", base64.b64encode(b"0123456789abcdef0123456789abcdef").decode("utf-8"))

    # Lazy imports after env setup
    import importlib

    import core.settings as core_settings
    import routers.secrets as secrets_router
    import main as app_main

    importlib.reload(core_settings)
    importlib.reload(secrets_router)
    importlib.reload(app_main)

    return TestClient(app_main.build_app())


def _h_internal() -> dict[str, str]:
    return {"X-Internal-Token": "itok"}


def _h_write() -> dict[str, str]:
    return {"X-Internal-Token": "itok", "X-Secret-Write-Token": "wtok"}


def test_store_resolve_rotate_revoke_exists(monkeypatch: pytest.MonkeyPatch, rows: dict) -> None:
    client = _build_client(monkeypatch)

    store = client.post("/secrets/store", json={"name": "identity-source/ldap/main-bind", "value": "secret-v1"}, headers=_h_write())
    assert store.status_code == 200
    ref = store.json()["data"]["ref"]
    assert ref == "sm://identity-source/ldap/main-bind"

    exists1 = client.get("/secrets/exists", params={"ref": ref}, headers=_h_internal())
    assert exists1.status_code == 200
    assert exists1.json()["data"]["exists"] is True

    resolved1 = client.post("/resolve", json={"ref": ref}, headers=_h_internal())
    assert resolved1.status_code == 200
    assert resolved1.json()["data"]["value"] == "secret-v1"

    rotate = client.post("/secrets/rotate", json={"ref": ref, "new_value": "secret-v2"}, headers=_h_write())
    assert rotate.status_code == 200

    resolved2 = client.post("/resolve", json={"ref": ref}, headers=_h_internal())
    assert resolved2.status_code == 200
    assert resolved2.json()["data"]["value"] == "secret-v2"

    assert "secret-v2" not in str(rows)

    revoke = client.post("/secrets/revoke", json={"ref": ref}, headers=_h_write())
    assert revoke.status_code == 200

    exists2 = client.get("/secrets/exists", params={"ref": ref}, headers=_h_internal())
    assert exists2.status_code == 200
    assert exists2.json()["data"]["exists"] is False

    assert ref not in rows


def test_rotate_of_an_unknown_secret_is_not_found(monkeypatch: pytest.MonkeyPatch, rows: dict) -> None:
    client = _build_client(monkeypatch)

    rotate = client.post("/secrets/rotate", json={"ref": "sm://capsule/none", "new_value": "v2"}, headers=_h_write())
    assert rotate.status_code == 404
    assert rows == {}


def test_invalid_prefix_rejected(monkeypatch: pytest.MonkeyPatch, rows: dict) -> None:
    client = _build_client(monkeypatch)

    r = client.post("/resolve", json={"ref": "env://DEV_PASSWORD"}, headers=_h_internal())
    assert r.status_code == 400
    assert ((r.json().get("error") or {}).get("code")) == "SECRET_INVALID_REF"


def test_path_traversal_rejected(monkeypatch: pytest.MonkeyPatch, rows: dict) -> None:
    client = _build_client(monkeypatch)

    r = client.post("/resolve", json={"ref": "sm://../etc/passwd"}, headers=_h_internal())
    assert r.status_code == 400
    assert ((r.json().get("error") or {}).get("code")) == "SECRET_INVALID_REF"


def test_auth_failure(monkeypatch: pytest.MonkeyPatch, rows: dict) -> None:
    client = _build_client(monkeypatch)

    r = client.post("/resolve", json={"ref": "sm://capsule/test"}, headers={"X-Internal-Token": "bad"})
    assert r.status_code == 403


def test_missing_secret(monkeypatch: pytest.MonkeyPatch, rows: dict) -> None:
    client = _build_client(monkeypatch)

    r = client.post("/resolve", json={"ref": "sm://missing/not-found"}, headers=_h_internal())
    assert r.status_code == 404
    assert ((r.json().get("error") or {}).get("code")) == "SECRET_NOT_FOUND"


def test_boot_failure_missing_master_key(monkeypatch: pytest.MonkeyPatch, rows: dict) -> None:
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("INTERNAL_TOKEN", "itok")
    monkeypatch.setenv("B2S_SECRET_ALLOWED_PREFIXES", "sm://")
    monkeypatch.delenv("B2S_SECRET_MASTER_KEY", raising=False)

    import importlib
    import core.settings as core_settings
    import routers.secrets as secrets_router

    importlib.reload(core_settings)
    importlib.reload(secrets_router)

    with pytest.raises(RuntimeError):
        secrets_router.ensure_boot_checks()
