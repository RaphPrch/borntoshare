import base64
import json
import struct
from pathlib import Path
from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from backend.app import install, license_keys
from backend.app.license import LicenseError, decode
from backend.app.main import app
from backend.app.migrations_runner import split_statements

client = TestClient(app)
PASSWORD = "Str0ng!Password"


def _key(payload: dict, private: Ed25519PrivateKey) -> str:
    # The format of scripts/license/issue_license.py
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    head = struct.pack(">BH", 1, len(body))
    text = base64.b32encode(head + body + private.sign(head + body)).decode().rstrip("=")
    return "B2S-" + "-".join(text[i:i + 5] for i in range(0, len(text), 5))


@pytest.fixture
def issuer(monkeypatch):
    private = Ed25519PrivateKey.generate()
    pem = private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    monkeypatch.setattr(license_keys, "PUBLIC_KEYS", [pem])
    return private


def _plan(**over):
    plan = {
        "server": {"host": "db", "port": 3306, "user": "root", "password": "x"},
        "app": {"db_name": "borntoshare", "logging_db_name": "borntoshare_logging", "user": "app_user", "password": PASSWORD},
        "admin": {"username": "admin", "email": "", "password": PASSWORD},
        "license": None,
        "fives": None,
    }
    plan.update(over)
    return plan


def test_public_keys_are_the_ones_of_the_core():
    core = Path(__file__).resolve().parents[3] / "core-service" / "app" / "core" / "license_keys.py"
    if not core.exists():
        pytest.skip("core-service not next to the wizard")
    namespace: dict = {}
    exec(core.read_text(), namespace)
    assert namespace["PUBLIC_KEYS"] == license_keys.PUBLIC_KEYS


def test_defaults_come_from_env_without_password(monkeypatch):
    monkeypatch.setenv("DB_HOST", "192.168.100.12")
    monkeypatch.setenv("DB_USER", "app_user")
    monkeypatch.setenv("DB_PASSWORD", "secret")
    data = client.get("/api/defaults").json()
    assert data["server"]["host"] == "192.168.100.12"
    assert data["app"] == {"db_name": "borntoshare", "logging_db_name": "borntoshare_logging", "user": "app_user"}
    assert data["fives"]["db_name"] == "b2s_fives"
    assert "secret" not in json.dumps(data)


def test_license_check(issuer):
    key = _key({"lic": "L1", "cust": "CORP", "feat": ["fives", "later"], "iat": "2026-01-01", "exp": "2099-12-31"}, issuer)
    response = client.post("/api/license/check", json={"key": key.lower().replace("-", " ")})
    assert response.status_code == 200
    data = response.json()
    assert data["customer"] == "CORP"
    assert [(f["key"], f["known"]) for f in data["features"]] == [("fives", True), ("later", False)]


def test_license_refused(issuer):
    other = Ed25519PrivateKey.generate()
    assert client.post("/api/license/check", json={"key": _key({"lic": "L", "cust": "C", "feat": ["fives"]}, other)}).status_code == 400
    assert client.post("/api/license/check", json={"key": "B2S-NOT-A-KEY"}).status_code == 400
    with pytest.raises(LicenseError, match="expiré"):
        decode(_key({"lic": "L", "cust": "C", "feat": ["fives"], "exp": "2020-01-01"}, issuer))
    with pytest.raises(LicenseError, match="aucun module"):
        decode(_key({"lic": "L", "cust": "C", "feat": ["later"]}, issuer))


@pytest.mark.parametrize("over, message", [
    ({"app": {"db_name": "bad-name", "logging_db_name": "l", "user": "u", "password": PASSWORD}}, "Base de données"),
    ({"app": {"db_name": "a", "logging_db_name": "a", "user": "u", "password": PASSWORD}}, "propre nom"),
    ({"app": {"db_name": "a", "logging_db_name": "b", "user": "root", "password": PASSWORD}}, "réservé"),
    ({"app": {"db_name": "a", "logging_db_name": "b", "user": "u", "password": "short"}}, "12 caractères"),
    ({"admin": {"username": "admin", "password": "Admin!Password1"}}, "identifiant"),
    ({"fives": {"db_name": "f", "inventory_db_name": "i", "user": "f", "password": PASSWORD}}, "ne l'ouvre pas"),
])
def test_plan_refused(over, message):
    response = client.post("/api/install", json=_plan(**over))
    assert response.status_code == 400
    assert message in response.json()["detail"]


def test_plan_with_module(issuer):
    key = _key({"lic": "L1", "cust": "CORP", "feat": ["fives"]}, issuer)
    fives = {"db_name": "b2s_fives", "inventory_db_name": "b2s_fives_inventory", "user": "app_user", "password": PASSWORD}
    with pytest.raises(install.InstallError, match="propre compte"):
        install.validate(_plan(license=key, fives=fives))
    plan = install.validate(_plan(license=key, fives={**fives, "user": "b2s_fives"}))
    assert plan["fives"]["user"] == "b2s_fives" and plan["license"].customer == "CORP"


def test_install_stops_at_the_first_failure():
    plan = install.validate(_plan())
    with patch.object(install, "_create", return_value=["borntoshare"]), \
         patch.object(install, "run_schema_pack", side_effect=RuntimeError("table x: syntax error")), \
         patch.object(install, "create_local_admin_if_needed") as admin:
        result = install.run(plan)
    assert result["ok"] is False
    assert [(s["key"], s["ok"]) for s in result["steps"]] == [("databases", True), ("packs", False)]
    assert "syntax error" in result["steps"][1]["detail"]
    assert "déjà présente" in result["steps"][0]["detail"]  # borntoshare_logging was there
    admin.assert_not_called()


def test_install_all_steps_and_env_without_passwords(issuer):
    key = _key({"lic": "L1", "cust": "CORP", "feat": ["fives"]}, issuer)
    plan = install.validate(_plan(license=key, fives={"db_name": "b2s_fives", "inventory_db_name": "b2s_fives_inventory",
                                                       "user": "b2s_fives", "password": PASSWORD}))
    with patch.object(install, "_create", side_effect=lambda server, names, user, password: list(names)), \
         patch.object(install, "run_schema_pack", return_value=40), patch.object(install, "run_logging_schema_pack", return_value=2), \
         patch.object(install, "create_local_admin_if_needed"), patch.object(install, "_license") as lic, \
         patch.object(install, "_opens"):
        result = install.run(plan)
    assert result["ok"] is True
    assert [s["key"] for s in result["steps"]] == ["databases", "packs", "admin", "license", "fives", "check"]
    assert lic.call_args.args[4] == ["fives"]
    env = dict(result["env"])
    assert env["DB_PASSWORD"] is None and env["FIVES_DB_PASSWORD"] is None
    assert env["FIVES_DB_USER"] == "b2s_fives" and env["LOGGING_DB_NAME"] == "borntoshare_logging"
    assert PASSWORD not in json.dumps(result)


def test_split_statements():
    sql = "-- comment\nCREATE TABLE a (\n  id INT\n);\n\nINSERT INTO a VALUES (1);\nSELECT 1"
    assert split_statements(sql) == ["CREATE TABLE a (\n  id INT\n)", "INSERT INTO a VALUES (1)", "SELECT 1"]


def test_page_and_health():
    assert client.get("/health").json() == {"status": "ok"}
    page = client.get("/")
    assert page.status_code == 200 and "Installation" in page.text
    assert client.get("/static/app.js").status_code == 200
