"""Storage topology: states, aggregation, incomplete data, volumes, and who may read it."""
from __future__ import annotations

from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import storage_topology as routes
from app.core.db import get_db
from app.services.storage_topology import (
    _sum_capacity,
    aggregate,
    counts_state,
    is_stale,
    probe_state,
    server_state,
    share_unc,
    volume_of,
)

STALE_BEFORE = datetime(2026, 11, 25, 8, 0, 0)


def test_probe_states_never_confuse_missing_data_with_an_outage() -> None:
    assert probe_state("success") == "available"
    assert probe_state("failed") == "unavailable"
    # Never probed, running, or a value this version does not know: unknown, not unavailable
    for value in (None, "", "running", "unknown", "weird"):
        assert probe_state(value) == "unknown"
    # A server switched off is not « down »
    assert probe_state("failed", active=False) == "unknown"


def test_stale_is_said_beside_the_state() -> None:
    assert is_stale(datetime(2026, 11, 20), STALE_BEFORE)
    assert not is_stale(datetime(2026, 11, 25, 9), STALE_BEFORE)
    assert is_stale("2026-11-20T10:00:00Z", STALE_BEFORE)
    # Never collected: unknown, not stale
    assert not is_stale(None, STALE_BEFORE) and not is_stale("not a date", STALE_BEFORE)


def test_parents_aggregate_their_children() -> None:
    assert aggregate(["available", "available"]) == "available"
    assert aggregate(["unavailable", "unavailable"]) == "unavailable"
    assert aggregate(["available", "unavailable"]) == "degraded"
    assert aggregate(["degraded", "available"]) == "degraded"
    # Unknown children are left out; none known (or no child at all): unknown
    assert aggregate(["available", "unknown"]) == "available"
    assert aggregate(["unknown", "unknown"]) == "unknown" and aggregate([]) == "unknown"
    assert counts_state(3, 0) == "available" and counts_state(0, 2) == "unavailable" and counts_state(1, 1) == "degraded"
    assert counts_state(0, 0) == "unknown"


def test_server_state_from_itself_and_its_folders() -> None:
    assert server_state("success", active=True, roots_failed=0, roots_ok=5) == "available"
    assert server_state("success", active=True, roots_failed=2, roots_ok=5) == "degraded"
    assert server_state("failed", active=True, roots_failed=0, roots_ok=0) == "unavailable"
    # Never probed itself: known through its folders, or unknown
    assert server_state(None, active=True, roots_failed=0, roots_ok=3) == "available"
    assert server_state(None, active=True, roots_failed=0, roots_ok=0) == "unknown"
    assert server_state("success", active=False, roots_failed=1, roots_ok=1) == "unknown"


def test_relations_volume_and_share_only_when_known() -> None:
    assert volume_of("D:\\Partages\\Finance") == "D:" and volume_of("e:/data") == "E:"
    # No FSRM reading, or a path that does not say it: no volume (the share hangs under its server)
    assert volume_of(None) is None and volume_of("\\\\fs\\share") is None and volume_of("Partages") is None
    assert share_unc("\\\\FS01\\Finance\\Compta") == "\\\\FS01\\Finance" and share_unc("FS01") is None


def test_capacity_sums_keep_unknown_apart_from_zero() -> None:
    assert _sum_capacity([{"quota_limit_bytes": None, "quotas": 0}, {"quota_limit_bytes": None, "quotas": 0}]) == {"quota_limit_bytes": None, "quotas": 0}
    assert _sum_capacity([{"quota_limit_bytes": 10}, {"quota_limit_bytes": None}, {"quota_limit_bytes": 5}]) == {"quota_limit_bytes": 15}
    assert _sum_capacity([None, {}]) == {}


# ---------------------------------------------------------------- who may read it


class _Topology:
    def __init__(self, db) -> None:
        pass

    def overview(self):
        return {"zones": []}

    def server(self, endpoint_id):
        return None


def _client(monkeypatch) -> TestClient:
    monkeypatch.setattr(routes, "StorageTopology", _Topology)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_db] = lambda: None
    return TestClient(app)


def test_only_administrators_read_the_topology(monkeypatch) -> None:
    client = _client(monkeypatch)
    # Hosts and probe messages of the servers: not for a guardian nor a user
    for roles in ("guardian", "user", ""):
        assert client.get("/storage-topology", headers={"x-identity-id": "7", "x-roles": roles}).status_code == 403
    assert client.get("/storage-topology/servers/1", headers={"x-identity-id": "7", "x-roles": "guardian"}).status_code == 403
    response = client.get("/storage-topology", headers={"x-identity-id": "1", "x-roles": "platform_admin"})
    assert response.status_code == 200 and response.json()["data"] == {"zones": []}


def test_an_unknown_server_is_not_found(monkeypatch) -> None:
    client = _client(monkeypatch)
    assert client.get("/storage-topology/servers/999", headers={"x-identity-id": "1", "x-roles": "admin"}).status_code == 404
    # A volume is a drive letter, nothing else
    assert client.get("/storage-topology/servers/1/roots?volume=D:%25", headers={"x-identity-id": "1", "x-roles": "admin"}).status_code == 422
