"""Diagnostic of the installation: results and severities from real measures, unknown when a check cannot run,
never a secret in the report."""
from __future__ import annotations

import json
from collections import namedtuple
from datetime import datetime, timedelta, timezone

from app.services import diagnostics

Usage = namedtuple("Usage", "total used free")


def test_disk_thresholds(monkeypatch) -> None:
    for used, expected in ((50, "ok"), (86, "warning"), (96, "error")):
        monkeypatch.setattr(diagnostics.shutil, "disk_usage", lambda _p, u=used: Usage(100 * 1024**3, u * 1024**3, (100 - u) * 1024**3))
        check = diagnostics._disk()
        assert check["result"] == expected and check["values"]["percent"] == used
    assert check["severity"] == "critical"


def test_a_check_that_cannot_run_is_unknown_not_a_failure_of_the_report() -> None:
    def broken():
        raise RuntimeError("database gone")

    [check] = diagnostics._guarded("jobs.queue", "jobs", "high", broken)
    assert check["result"] == "unknown" and check["code"] == "jobs.queue"


def test_the_internal_token_is_measured_never_shown(monkeypatch) -> None:
    monkeypatch.setenv("INTERNAL_TOKEN", "s3cr3t-value-that-must-not-leak-0123456789")
    check = diagnostics._internal_token()
    assert check["result"] == "ok" and "s3cr3t" not in json.dumps(check)
    monkeypatch.setenv("INTERNAL_TOKEN", "short")
    assert diagnostics._internal_token()["result"] == "error"


class _Rows:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def __iter__(self):
        return iter(self.rows)


class _Db:
    def __init__(self, schedule, components):
        self.schedule, self.components = schedule, components

    def execute(self, statement, params=None):
        return _Rows(self.schedule if "infra_schedules" in str(statement) else self.components)


def test_components_are_grouped_with_the_names_of_those_down() -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    db = _Db([{"interval_minutes": 5, "is_enabled": 1, "last_run_at": now}], [
        {"component": "identity_source:1", "label": "Directory · Siège", "status": "down", "checked_at": now},
        {"component": "identity_source:2", "label": "Directory · Usines", "status": "healthy", "checked_at": now},
        {"component": "storage_endpoint:9", "label": "File server · FILER01", "status": "down", "checked_at": now},
    ])
    checks = {c["code"]: c for c in diagnostics._components(db)}
    assert checks["health.schedule"]["result"] == "ok"
    assert checks["components.directories"]["result"] == "warning" and checks["components.directories"]["values"]["names"] == ["Siège"]
    assert checks["components.file_servers"]["result"] == "error"  # every file server down
    assert "components.sso" not in checks  # nothing configured: no check, not a fake « ok »


def test_a_health_check_that_no_longer_runs_is_reported() -> None:
    old = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=2)
    [schedule] = diagnostics._components(_Db([{"interval_minutes": 5, "is_enabled": 1, "last_run_at": old}], []))
    assert schedule["result"] == "warning" and schedule["values"]["last_run_minutes"] >= 119


def test_only_an_administrator_runs_the_diagnostic(monkeypatch) -> None:
    import pytest
    from fastapi import HTTPException
    from starlette.requests import Request

    from app.api import infrastructure

    ran = []
    monkeypatch.setattr(diagnostics, "run", lambda db: ran.append(db) or {"checks": []})

    def request(roles: str) -> Request:
        headers = [(b"x-identity-id", b"7"), (b"x-roles", roles.encode())]
        return Request({"type": "http", "method": "GET", "path": "/api/infrastructure/diagnostics", "headers": headers})

    with pytest.raises(HTTPException) as exc:
        infrastructure.get_diagnostics(request("user"), db=object())
    assert exc.value.status_code == 403 and not ran
    assert infrastructure.get_diagnostics(request("platform_admin"), db=object())["data"] == {"checks": []}
