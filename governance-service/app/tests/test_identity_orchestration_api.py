from __future__ import annotations

import asyncio
import pytest
from fastapi import HTTPException

from app.api import identity_orchestration as api


class _Req:
    def __init__(self, payload: dict | None = None, headers: dict | None = None, query: dict | None = None):
        self._payload = dict(payload or {})
        self.headers = dict(headers or {})
        self.query_params = dict(query or {})

    async def json(self) -> dict:
        return dict(self._payload)


def test_search_identity_returns_data_envelope(monkeypatch) -> None:
    async def _fake_search_identity_service(incoming: dict):
        assert incoming.get("query") == "alice"
        return {
            "items": [{"id": "a1"}],
            "users": [],
            "groups": [],
            "ous": [],
            "snapshot_id": 123,
            "snapshot_status": "ACTIVE",
        }

    monkeypatch.setattr(api, "search_identity_service", _fake_search_identity_service)

    out = asyncio.run(api.search_identity(_Req({"identity_source_id": 12, "query": "alice"})))
    assert "data" in out
    assert out["data"]["items"][0]["id"] == "a1"
    assert out["data"]["snapshot_id"] == 123
    assert out["data"]["snapshot_status"] == "ACTIVE"


def test_list_identity_overview_returns_list_envelope(monkeypatch) -> None:
    async def _fake_list_identity_overview_service(query_params: dict):
        assert query_params.get("status") == "active"
        return [{"id": 1}, {"id": 2}]

    monkeypatch.setattr(api, "list_identity_overview_service", _fake_list_identity_overview_service)

    out = asyncio.run(api.list_identity_overview(_Req(query={"status": "active"})))
    assert out["data"] == [{"id": 1}, {"id": 2}]
    assert out["meta"]["count"] == 2


def test_import_identity_ad_enveloped(monkeypatch) -> None:
    async def _fake_import_identity_ad_service(incoming: dict):
        _ = incoming
        return {"found": True, "identity_id": "42", "item": {"index": 0}}

    monkeypatch.setattr(api, "import_identity_ad_service", _fake_import_identity_ad_service)

    out = asyncio.run(api.import_identity_ad(_Req({"identity_source_id": 3, "principal": {"username": "alice"}})))
    assert out["data"]["found"] is True
    assert out["data"]["identity_id"] == "42"


def test_import_identity_ad_requires_identity_source_id(monkeypatch) -> None:
    async def _fake_import_identity_ad_service(incoming: dict):
        raise HTTPException(status_code=422, detail={"error_code": "IDENTITY_SOURCE_ID_REQUIRED", "incoming": incoming})

    monkeypatch.setattr(api, "import_identity_ad_service", _fake_import_identity_ad_service)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(api.import_identity_ad(_Req({"principal": {"username": "alice"}})))
    assert exc.value.status_code == 422


def test_discover_identity_and_job_are_enveloped(monkeypatch) -> None:
    async def _fake_discover_identity_service(incoming: dict, request_id: str | None = None):
        assert incoming.get("identity_source_id") == 5
        assert request_id == "rid-1"
        return {"job_id": 987, "status": "queued", "correlation_id": "rid-1"}

    async def _fake_get_identity_job_service(job_id: int):
        assert job_id == 33
        return {"job_id": "33", "status": "succeeded", "result": {"items": []}, "metrics": {}, "error": {}}

    monkeypatch.setattr(api, "discover_identity_service", _fake_discover_identity_service)
    monkeypatch.setattr(api, "get_identity_job_service", _fake_get_identity_job_service)

    out_discover = asyncio.run(
        api.discover_identity(
            _Req({"identity_source_id": 5, "query": "alice"}, headers={"x-request-id": "rid-1"})
        )
    )
    out_job = asyncio.run(api.get_identity_job(33))

    assert out_discover["data"]["job_id"] == 987
    assert out_discover["data"]["status"] == "queued"
    assert out_job["data"]["job_id"] == "33"
    assert out_job["data"]["status"] == "succeeded"


def test_run_identity_snapshot_enveloped(monkeypatch) -> None:
    async def _fake_run_identity_snapshot_service(incoming: dict, request_id: str | None = None):
        assert incoming.get("identity_source_id") == 9
        assert request_id == "rid-snap"
        return {"job_id": 654, "snapshot_id": 321, "status": "queued", "correlation_id": "rid-snap"}

    monkeypatch.setattr(api, "run_identity_snapshot_service", _fake_run_identity_snapshot_service)

    out = asyncio.run(
        api.run_identity_snapshot(
            _Req({"identity_source_id": 9, "mode": "auto", "force_full": True}, headers={"x-request-id": "rid-snap"})
        )
    )
    assert out["data"]["job_id"] == 654
    assert out["data"]["snapshot_id"] == 321
    assert out["data"]["status"] == "queued"
