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

TOKEN = "one-time-token-of-the-tests"
client = TestClient(app, headers={"X-Wizard-Token": TOKEN})
PASSWORD = "Str0ng!Password"


@pytest.fixture(autouse=True)
def _token(monkeypatch):
    # make wizard writes it in secrets/.wizard-token
    from backend.app import main

    monkeypatch.setattr(main, "expected_token", lambda: TOKEN)


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
        "app": {"db_name": "borntoshare", "logging_db_name": "borntoshare_logging", "user": "b2s_core", "migrate_user": "b2s_migrate"},
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
    assert data["app"] == {"db_name": "borntoshare", "logging_db_name": "borntoshare_logging", "user": "app_user", "migrate_user": "b2s_migrate"}
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
    ({"app": {"db_name": "bad-name", "logging_db_name": "l", "user": "u", "migrate_user": "m"}}, "Base de données"),
    ({"app": {"db_name": "a", "logging_db_name": "a", "user": "u", "migrate_user": "m"}}, "propre nom"),
    ({"app": {"db_name": "a", "logging_db_name": "b", "user": "root", "migrate_user": "m"}}, "réservé"),
    ({"app": {"db_name": "a", "logging_db_name": "b", "user": "same", "migrate_user": "same"}}, "propre compte"),
    ({"admin": {"username": "admin", "password": "Admin!Password1"}}, "identifiant"),
    ({"fives": {"db_name": "f", "inventory_db_name": "i", "user": "f"}}, "ne l'ouvre pas"),
    ({"modules": {"governance": False, "fives": False}}, "Modules"),
])
def test_plan_refused(over, message):
    response = client.post("/api/install", json=_plan(**over))
    assert response.status_code == 400
    assert message in response.json()["detail"]


def test_plan_with_module(issuer):
    key = _key({"lic": "L1", "cust": "CORP", "feat": ["fives"]}, issuer)
    fives = {"db_name": "b2s_fives", "inventory_db_name": "b2s_fives_inventory", "user": "b2s_core"}
    with pytest.raises(install.InstallError, match="propre compte"):
        install.validate(_plan(license=key, fives=fives))
    plan = install.validate(_plan(license=key, fives={**fives, "user": "b2s_fives"}))
    assert plan["fives"]["user"] == "b2s_fives" and plan["license"].customer == "CORP"


def test_install_stops_at_the_first_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRETS_DIR", str(tmp_path))
    plan = install.validate(_plan())
    with patch.object(install, "_databases_and_accounts", return_value=["borntoshare"]), \
         patch.object(install, "run_schema_pack", side_effect=RuntimeError("table x: syntax error")), \
         patch.object(install, "create_local_admin_if_needed") as admin:
        result = install.run(plan)
    assert result["ok"] is False
    assert [(s["key"], s["ok"]) for s in result["steps"]] == [("secrets", True), ("databases", True), ("packs", False)]
    assert "syntax error" in result["steps"][2]["detail"]
    assert "déjà présente" in result["steps"][1]["detail"]  # borntoshare_logging was there
    admin.assert_not_called()
    # The passwords given to the accounts are kept even though the installation stopped after
    assert sorted(p.name for p in tmp_path.iterdir()) == ["b2s_db_core", "b2s_db_migrate"]


def test_install_refuses_without_the_secrets_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRETS_DIR", str(tmp_path / "missing"))
    with patch.object(install, "_databases_and_accounts") as create:
        result = install.run(install.validate(_plan()))
    assert result["ok"] is False and result["steps"][0]["key"] == "secrets"
    create.assert_not_called()


def test_install_all_steps_writes_the_secrets_and_no_password_on_screen(issuer, tmp_path, monkeypatch):
    monkeypatch.setenv("SECRETS_DIR", str(tmp_path))
    key = _key({"lic": "L1", "cust": "CORP", "feat": ["fives"]}, issuer)
    plan = install.validate(_plan(license=key, fives={"db_name": "b2s_fives", "inventory_db_name": "b2s_fives_inventory", "user": "b2s_fives"}))
    given: dict = {}
    with patch.object(install, "_databases_and_accounts", side_effect=lambda server, app, fives, passwords: given.update(passwords) or []), \
         patch.object(install, "run_schema_pack", return_value=40) as schema, patch.object(install, "run_logging_schema_pack", return_value=2), \
         patch.object(install, "run_fives_packs", return_value=2), patch.object(install, "create_local_admin_if_needed"), \
         patch.object(install, "_license") as lic, patch.object(install, "_switch") as switch, patch.object(install, "_check_account") as check:
        result = install.run(plan)
    assert result["ok"] is True
    assert [s["key"] for s in result["steps"]] == ["secrets", "databases", "packs", "admin", "license", "modules", "check"]
    # Both modules: the governance stays on
    assert switch.call_args.args[2:4] == ("governance", True)
    # The packs with the migration account, not the administrator
    assert schema.call_args.args[1]["user"] == "b2s_migrate"
    assert lic.call_args.args[4] == ["fives"]
    assert [c.args[1] for c in check.call_args_list] == ["b2s_core", "b2s_fives"]
    files = {p.name: p for p in tmp_path.iterdir() if p.name.startswith("b2s_")}
    assert sorted(files) == ["b2s_db_core", "b2s_db_fives", "b2s_db_migrate"]
    assert {name: oct(path.stat().st_mode & 0o777) for name, path in files.items()} == dict.fromkeys(files, "0o600")
    assert files["b2s_db_core"].read_text() == given["core"] and len(given["core"]) == 40
    assert len(set(given.values())) == 3
    # The defaults are not repeated: .env needs the server only
    assert result["env"] == [["DB_HOST", "db"]]
    text = json.dumps(result)
    assert all(value not in text for value in given.values()) and PASSWORD not in text


def test_split_statements():
    sql = "-- comment\nCREATE TABLE a (\n  id INT\n);\n\nINSERT INTO a VALUES (1);\nSELECT 1"
    assert split_statements(sql) == ["CREATE TABLE a (\n  id INT\n)", "INSERT INTO a VALUES (1)", "SELECT 1"]


def test_page_and_health():
    assert client.get("/health").json() == {"status": "ok"}
    page = client.get("/")
    assert page.status_code == 200 and "Installation" in page.text
    assert client.get("/static/app.js").status_code == 200


def test_env_lines_only_for_names_other_than_the_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRETS_DIR", str(tmp_path))
    plan = install.validate(_plan(app={"db_name": "b2s_prod", "logging_db_name": "borntoshare_logging", "user": "b2s_core", "migrate_user": "b2s_migrate"}))
    with patch.object(install, "_databases_and_accounts", return_value=[]), patch.object(install, "run_schema_pack"), \
         patch.object(install, "run_logging_schema_pack"), patch.object(install, "create_local_admin_if_needed"), patch.object(install, "_check_account"):
        result = install.run(plan)
    assert result["env"] == [["DB_HOST", "db"], ["DB_NAME", "b2s_prod"]]


def test_a_successful_installation_signals_the_watcher(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRETS_DIR", str(tmp_path))
    with patch.object(install, "_databases_and_accounts", return_value=[]), patch.object(install, "run_schema_pack"), \
         patch.object(install, "run_logging_schema_pack"), patch.object(install, "create_local_admin_if_needed"), patch.object(install, "_check_account"), \
         patch.object(install, "_switch"):
        install.run(install.validate(_plan()))
    assert json.loads((tmp_path / ".installed").read_text()) == {"env": [["DB_HOST", "db"]]}
    assert client.get("/api/deploy").json()["state"] == "waiting"


def test_no_signal_when_the_installation_stops(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRETS_DIR", str(tmp_path))
    with patch.object(install, "_databases_and_accounts", side_effect=RuntimeError("denied")):
        install.run(install.validate(_plan()))
    assert not (tmp_path / ".installed").exists()


def test_deploy_status_follows_the_phases_of_deploy(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRETS_DIR", str(tmp_path))
    monkeypatch.setenv("FRONTEND_PUBLIC_ORIGIN", "https://b2s.example")
    (tmp_path / ".deploy-status").write_text('{"state": "running", "phase": "3/4 build + recreate: core-service"}')
    data = client.get("/api/deploy").json()
    assert (data["state"], data["phase_index"], data["app_url"]) == ("running", 3, "https://b2s.example")
    (tmp_path / ".deploy-status").write_text('{"state": "failed", "phase": "Error: build"}')
    (tmp_path / ".deploy.log").write_text("0/4 secrets\nError: build\n")
    data = client.get("/api/deploy").json()
    assert data["state"] == "failed" and data["log"][-1] == "Error: build"
    (tmp_path / ".deploy-status").write_text('{"state": "done", "phase": "BornToShare est démarré"}')
    assert client.get("/api/deploy").json()["phase_index"] == 5


def test_a_5s_only_installation_switches_the_governance_off(issuer, tmp_path, monkeypatch):
    monkeypatch.setenv("SECRETS_DIR", str(tmp_path))
    key = _key({"lic": "L1", "cust": "CORP", "feat": ["fives"]}, issuer)
    plan = install.validate(_plan(license=key, modules={"governance": False, "fives": True},
                                  fives={"db_name": "b2s_fives", "inventory_db_name": "b2s_fives_inventory", "user": "b2s_fives"}))
    assert plan["governance"] is False
    with patch.object(install, "_databases_and_accounts", return_value=[]), patch.object(install, "run_schema_pack", return_value=1), \
         patch.object(install, "run_logging_schema_pack", return_value=1), patch.object(install, "run_fives_packs", return_value=1), \
         patch.object(install, "create_local_admin_if_needed"), patch.object(install, "_license"), \
         patch.object(install, "_switch") as switch, patch.object(install, "_check_account"):
        result = install.run(plan)
    assert result["ok"] is True
    switch.assert_called_once()
    assert switch.call_args.args[2:4] == ("governance", False)


def test_the_first_administrator_changes_its_password_at_the_first_sign_in():
    from backend.app import admin_logic
    import inspect

    source = inspect.getsource(admin_logic.create_local_admin_if_needed)
    # Created or synchronised by the wizard: its password is temporary in both cases
    assert source.count("must_change_password") >= 2


def test_the_api_needs_the_token_of_make_wizard(tmp_path, monkeypatch):
    from backend.app import main

    stranger = TestClient(app)
    assert stranger.get("/api/defaults").status_code == 403
    assert TestClient(app, headers={"X-Wizard-Token": "guess"}).get("/api/defaults").status_code == 403
    assert stranger.post("/api/install", json={}).status_code == 403
    # The page itself holds nothing: it opens, then asks for the right address
    assert stranger.get("/").status_code == 200 and stranger.get("/health").status_code == 200
    # No token file (not started by make wizard): nobody gets in
    monkeypatch.undo()
    monkeypatch.setenv("SECRETS_DIR", str(tmp_path))
    assert client.get("/api/defaults").status_code == 403
    (tmp_path / main.TOKEN_FILE).write_text(TOKEN + "\n")
    assert client.get("/api/defaults").status_code == 200
