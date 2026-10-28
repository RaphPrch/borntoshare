from __future__ import annotations

import socket
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app import main as agent  # noqa: E402
from app.actions import infra_health  # noqa: E402
from app.core import settings  # noqa: E402


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_USERNAME", "b2s-agent")
    monkeypatch.setattr(settings, "AGENT_PASSWORD", "s3cret")
    monkeypatch.setattr(agent, "_dramatiq_processes", lambda: 4)
    monkeypatch.setattr(agent, "_broker_state", lambda: {"reachable": True, "latency_ms": 1, "queues": {"capsule_probes": 2}})
    return TestClient(agent.app)


def test_agent_requires_its_credentials(client) -> None:
    assert client.get("/agent/v1/info").status_code == 401
    assert client.get("/agent/v1/info", auth=("b2s-agent", "wrong")).status_code == 401
    ok = client.get("/agent/v1/info", auth=("b2s-agent", "s3cret"))
    assert ok.status_code == 200
    data = ok.json()["data"]
    assert data["status"] == "healthy"
    assert data["broker"]["queues"]["capsule_probes"] == 2


def test_agent_without_configured_credentials_refuses_everyone(monkeypatch) -> None:
    monkeypatch.setattr(settings, "AGENT_USERNAME", "")
    monkeypatch.setattr(settings, "AGENT_PASSWORD", "")
    assert TestClient(agent.app).get("/agent/v1/info", auth=("", "")).status_code == 503


def test_agent_is_degraded_without_job_process(client, monkeypatch) -> None:
    monkeypatch.setattr(agent, "_dramatiq_processes", lambda: 0)
    assert client.get("/agent/v1/info", auth=("b2s-agent", "s3cret")).json()["data"]["status"] == "degraded"


def test_health_check_reports_each_target(monkeypatch) -> None:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    open_port = listener.getsockname()[1]
    monkeypatch.setattr(infra_health, "check_http", lambda url, timeout, verify: {"status": "healthy", "latency_ms": 3, "message": "HTTP 200"})
    try:
        ok, _message, details = infra_health.run_infra_health_check({
            "targets": [
                {"component": "db", "kind": "tcp", "target": f"127.0.0.1:{open_port}"},
                {"component": "closed", "kind": "tcp", "target": "127.0.0.1:1"},
                {"component": "bad", "kind": "tcp", "target": "no-port"},
                {"component": "web", "kind": "http", "target": "http://web/health"},
            ],
            "timeout": 2,
        })
    finally:
        listener.close()
    by = {r["component"]: r for r in details["results"]}
    assert ok is True
    assert by["db"]["status"] == "healthy"
    assert by["closed"]["status"] == "down"
    assert by["bad"]["status"] == "down"
    assert by["web"]["status"] == "healthy"
    assert sorted(details["down"]) == ["bad", "closed"]
