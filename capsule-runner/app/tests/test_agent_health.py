from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import redis

from app import main as agent


class _Redis:
    def __init__(self, up: bool) -> None:
        self.up = up

    def ping(self) -> None:
        if not self.up:
            raise ConnectionError("redis down")


def test_health_needs_a_dramatiq_process_and_the_job_queue(monkeypatch) -> None:
    client = TestClient(agent.app)

    monkeypatch.setattr(agent, "_dramatiq_processes", lambda: 2)
    monkeypatch.setattr(redis.Redis, "from_url", classmethod(lambda cls, *a, **k: _Redis(True)))
    up = client.get("/health")
    assert up.status_code == 200 and up.json()["data"]["checks"] == {"workers": "ok", "job_queue": "ok"}

    monkeypatch.setattr(agent, "_dramatiq_processes", lambda: 0)
    down = client.get("/health")
    assert down.status_code == 503 and down.json()["ok"] is False
    assert down.json()["data"]["checks"]["workers"] == "no Dramatiq process"

    monkeypatch.setattr(agent, "_dramatiq_processes", lambda: 2)
    monkeypatch.setattr(redis.Redis, "from_url", classmethod(lambda cls, *a, **k: _Redis(False)))
    assert client.get("/health").status_code == 503
