"""TLS to MariaDB (DB_TLS): the arguments given to PyMySQL."""
import pytest

from app.core.config import Settings

BASE = {"DB_HOST": "db", "DB_PASSWORD": "x", "INTERNAL_TOKEN": "t", "CAPSULE_BROKER_URL": "redis://r:6379/2"}


def test_off_by_default():
    assert Settings(**BASE).db_connect_args == {}


def test_on_with_the_private_authority(tmp_path):
    ca = tmp_path / "db-ca.pem"
    ca.write_text("x")
    args = Settings(**BASE, DB_TLS="ON", DB_TLS_CA=str(ca)).db_connect_args
    assert args == {"ssl_ca": str(ca), "ssl_verify_cert": True, "ssl_verify_identity": True}


def test_on_without_file_uses_the_system_authorities(tmp_path):
    args = Settings(**BASE, DB_TLS="on", DB_TLS_CA=str(tmp_path / "none.pem")).db_connect_args
    assert args["ssl_ca"] is None and args["ssl_verify_cert"] is True and args["ssl_verify_identity"] is True


def test_other_values_refused():
    with pytest.raises(ValueError):
        Settings(**BASE, DB_TLS="yes")
