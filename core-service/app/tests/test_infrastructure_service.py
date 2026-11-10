from __future__ import annotations

import json
from datetime import datetime, timedelta


from app.services import infrastructure_service as infra


class _Conn:
    """A connection answering the queries of database_info."""

    def __init__(self, grants):
        self.grants = grants

    def execute(self, statement, params=None):
        sql = str(statement)
        if "VERSION()" in sql:
            return _Scalar("11.4.13-MariaDB")
        if "GROUP BY table_schema" in sql:
            return _All([("borntoshare", 53), ("borntoshare_logging", 1)])
        if "SHOW GRANTS" in sql:
            return _All([(g,) for g in self.grants])
        return _All([(name,) for name in infra.REQUIRED_TABLES])


class _Scalar:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        return self.value


class _All:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows

    def __iter__(self):
        return iter(self.rows)


class _Db:
    def __init__(self, grants):
        self.conn = _Conn(grants)

    def connection(self):
        return self.conn


def test_database_info_shows_the_rights_of_the_account_without_its_password(monkeypatch) -> None:
    monkeypatch.setenv("DB_PASSWORD_FILE", "/run/secrets/b2s_db_core")
    info = infra.database_info(_Db([
        "GRANT USAGE ON *.* TO `b2s_core`@`%` IDENTIFIED BY PASSWORD '*ABCDEF0123'",
        "GRANT SELECT, INSERT, UPDATE, DELETE ON `borntoshare`.* TO `b2s_core`@`%`",
        "GRANT SELECT, INSERT, DELETE ON `borntoshare_logging`.* TO `b2s_core`@`%`",
    ]))
    assert info["ok"] is True and info["tables"] == 53 and info["logging_tables"] == 1
    assert info["schema_rights"] is False and info["password_from"] == "secret"
    assert len(info["grants"]) == 2
    assert "ABCDEF" not in json.dumps(info)


def test_database_info_warns_when_the_account_can_change_the_schema() -> None:
    info = infra.database_info(_Db(["GRANT ALL PRIVILEGES ON `borntoshare`.* TO `app_user`@`%`"]))
    assert info["schema_rights"] is True


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


class _WorkerDb:
    def __init__(self, existing: bool = False) -> None:
        self.existing = existing
        self.inserted: list[dict] = []
        self.committed = False

    def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        if sql.startswith("INSERT INTO infra_workers"):
            self.inserted.append(dict(params))
        return self

    def first(self):
        return (1,) if self.existing else None

    @property
    def lastrowid(self) -> int:
        return 1

    def commit(self) -> None:
        self.committed = True


def test_the_local_worker_declares_itself_on_the_port_where_its_agent_answers(monkeypatch) -> None:
    import asyncio

    async def check(row):
        return {"status": "healthy" if row["port"] == 8443 else "down"}

    monkeypatch.setattr(infra, "check_agent", check)
    monkeypatch.setattr(infra, "record_worker_check", lambda *a, **k: None)
    db = _WorkerDb()

    assert asyncio.run(infra.register_local_worker(db))["port"] == 8443
    assert db.inserted[0]["use_tls"] is True and db.committed is True


def test_no_local_worker_when_one_is_declared_or_none_answers(monkeypatch) -> None:
    import asyncio

    async def down(row):
        return {"status": "down"}

    monkeypatch.setattr(infra, "check_agent", down)
    assert asyncio.run(infra.register_local_worker(_WorkerDb(existing=True))) is None
    db = _WorkerDb()
    assert asyncio.run(infra.register_local_worker(db)) is None
    assert db.inserted == []
