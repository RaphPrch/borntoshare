from pathlib import Path

import pytest

from app import secret_files

ROOT = Path(__file__).resolve().parents[3]


def test_password_read_from_its_file(tmp_path):
    (tmp_path / "db").write_text("s3cret\n")
    (tmp_path / "redis").write_text("r3dis")
    env = {"DB_PASSWORD_FILE": str(tmp_path / "db"), "REDIS_PASSWORD_FILE": str(tmp_path / "redis"),
           "CAPSULE_BROKER_URL": "redis://redis:6379/2"}
    secret_files.load(env)
    assert env["DB_PASSWORD"] == "s3cret"
    assert env["CAPSULE_BROKER_URL"] == "redis://:r3dis@redis:6379/2"


def test_a_value_already_given_wins_and_a_url_with_password_is_kept(tmp_path):
    (tmp_path / "db").write_text("from-file")
    env = {"DB_PASSWORD": "given", "DB_PASSWORD_FILE": str(tmp_path / "db"), "REDIS_PASSWORD": "x/y",
           "CAPSULE_BROKER_URL": "redis://:other@redis:6379/2"}
    secret_files.load(env)
    assert env["DB_PASSWORD"] == "given"
    assert env["CAPSULE_BROKER_URL"] == "redis://:other@redis:6379/2"


def test_only_the_known_names_are_read(tmp_path):
    # LDAP_CA_FILE, B2S_AGENT_CA_FILE… also end in _FILE: they are paths, not secrets
    env = {"LDAP_CA_FILE": str(tmp_path / "ca.pem")}
    secret_files.load(env)
    assert env == {"LDAP_CA_FILE": str(tmp_path / "ca.pem")}


def test_same_loader_in_every_service():
    copies = [ROOT / d / "secret_files.py" for d in ("auth-service/app", "capsule-runner/app", "fives-service/app", "fives-scanner/scanner")]
    if not all(path.exists() for path in copies):
        pytest.skip("the other services are not next to core-service")
    mine = Path(secret_files.__file__).read_text()
    assert [path.read_text() == mine for path in copies] == [True] * len(copies)


def test_the_token_of_the_services_and_the_session_key_come_from_their_files(tmp_path):
    # make deploy generates them as podman secrets: nothing in .env, nothing in the environment of the container
    (tmp_path / "token").write_text("t" * 48 + "\n")
    (tmp_path / "key").write_text("k" * 48)
    env = {"INTERNAL_TOKEN_FILE": str(tmp_path / "token"), "PRINCIPAL_SIGNING_KEY_FILE": str(tmp_path / "key")}
    secret_files.load(env)
    assert env["INTERNAL_TOKEN"] == "t" * 48 and env["PRINCIPAL_SIGNING_KEY"] == "k" * 48
