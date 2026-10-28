from __future__ import annotations

import json
import os
from datetime import datetime, timedelta

import pytest

from app.core import config, runtime_config
from app.services import infrastructure_service as infra


@pytest.fixture()
def runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("B2S_RUNTIME_DIR", str(tmp_path))
    return tmp_path


def test_runtime_database_file_overrides_env_at_startup(runtime) -> None:
    runtime_config.write_database_config({"mode": "fields", "host": "db02.example.com", "port": 3307, "name": "b2s", "user": "app", "password": "pw", "logging_name": "b2s_log"})

    settings = config._apply_runtime_database(config.Settings())

    assert settings.DB_CONFIG_SOURCE == "runtime"
    assert settings.sqlalchemy_url.endswith("@db02.example.com:3307/b2s")
    assert settings.LOGGING_DB_HOST == "db02.example.com"
    assert settings.LOGGING_DB_NAME == "b2s_log"
    assert oct(os.stat(runtime_config.database_file()).st_mode & 0o777) == "0o600"


def test_dsn_override_wins_over_the_fields(runtime) -> None:
    runtime_config.write_database_config({"mode": "dsn", "dsn": "mariadb+pymysql://app:pw@db03.example.com:3306/b2s"})

    settings = config._apply_runtime_database(config.Settings())

    assert settings.sqlalchemy_url == "mariadb+pymysql://app:pw@db03.example.com:3306/b2s"
    assert settings.DB_HOST == "db03.example.com"


def test_without_file_the_env_settings_stay(runtime) -> None:
    settings = config._apply_runtime_database(config.Settings())
    assert settings.DB_CONFIG_SOURCE == "env"


def test_an_invalid_dsn_is_refused_before_any_connection(runtime) -> None:
    result = infra.test_database({"mode": "dsn", "dsn": "not a dsn"})
    assert result["ok"] is False


def test_a_database_cannot_be_saved_without_a_successful_test(runtime, monkeypatch) -> None:
    monkeypatch.setattr(infra, "test_database", lambda payload: {"ok": False, "message": "Connection failed"})
    with pytest.raises(ValueError):
        infra.save_database({"mode": "fields", "host": "db", "name": "b2s", "user": "app", "password": "pw"}, "admin")
    assert not runtime_config.database_file().exists()


def test_the_password_is_never_returned(runtime) -> None:
    runtime_config.write_database_config({"mode": "fields", "host": "db02", "port": 3306, "name": "b2s", "user": "app", "password": "pw"})
    info = infra.database_info()
    assert "pw" not in json.dumps(info)
    assert info["configured"]["has_password"] is True
    assert info["pending_restart"] is True


def test_agent_url_brackets_ipv6() -> None:
    assert infra.agent_url({"host": "fd00::5", "port": 8443, "use_tls": True}) == "https://[fd00::5]:8443"
    assert infra.agent_url({"host": "worker01", "port": 9000, "use_tls": False}) == "http://worker01:9000"


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def __iter__(self):
        return iter(self._rows)

    def scalar(self):
        return 5


class _DB:
    def __init__(self, status_rows, history_rows):
        self.status_rows, self.history_rows = status_rows, history_rows

    def execute(self, statement, params=None):
        sql = str(statement)
        if "FROM infra_component_status" in sql:
            return _Rows(self.status_rows)
        if "FROM infra_check_history" in sql:
            return _Rows(self.history_rows)
        return _Rows([])


def test_overview_marks_old_results_unknown_and_computes_uptime() -> None:
    now = datetime.utcnow()
    rows = [
        {"component": "web", "label": "Web", "category": "web", "status": "healthy", "latency_ms": 5, "message": "HTTP 200", "checked_by": "w", "details_json": None, "checked_at": now},
        {"component": "old", "label": "Old", "category": "custom", "status": "healthy", "latency_ms": 5, "message": "", "checked_by": "w", "details_json": None, "checked_at": now - timedelta(hours=2)},
    ]
    history = [
        {"component": "web", "status": s, "latency_ms": 5, "checked_at": now - timedelta(minutes=i)}
        for i, s in enumerate(["healthy", "healthy", "down", "healthy"])
    ]

    out = infra.overview(_DB(rows, history))

    by = {c["component"]: c for c in out["components"]}
    assert by["web"]["uptime_24h"] == 75.0
    assert by["old"]["status"] == "unknown" and by["old"]["stale"] is True
    assert out["summary"]["healthy"] == 1 and out["summary"]["unknown"] == 1
