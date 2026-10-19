from __future__ import annotations

import asyncio
from datetime import datetime

import pytest
from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel

from app.core import direct_call


class _Payload(BaseModel):
    name: str
    count: int = 1


def _get_db():  # pragma: no cover - replaced by direct_call
    yield None


def _handler(item_id: int, payload: _Payload, limit: int = Query(default=25), db=Depends(_get_db)):
    return {"item_id": item_id, "name": payload.name, "count": payload.count, "limit": limit, "has_db": db is not None, "at": datetime(2026, 1, 2)}


async def _async_handler(item_id: int, db=Depends(_get_db)):
    if item_id == 404:
        raise HTTPException(status_code=404, detail="not found")
    return {"item_id": item_id}


class _FakeSession:
    closed = False

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def session(monkeypatch):
    fake = _FakeSession()
    monkeypatch.setattr(direct_call, "SessionLocal", lambda: fake)
    return fake


def test_call_route_validates_payload_fills_query_defaults_and_encodes(session) -> None:
    out = asyncio.run(direct_call.call_route(_handler, item_id=3, payload={"name": "x"}))
    assert out == {"item_id": 3, "name": "x", "count": 1, "limit": 25, "has_db": True, "at": "2026-01-02T00:00:00"}
    assert session.closed


def test_call_route_rejects_invalid_payload_with_422(session) -> None:
    with pytest.raises(HTTPException) as exc:
        asyncio.run(direct_call.call_route(_handler, item_id=3, payload={"count": 2}))
    assert exc.value.status_code == 422


def test_call_route_propagates_http_exceptions_from_async_handlers(session) -> None:
    assert asyncio.run(direct_call.call_route(_async_handler, item_id=1)) == {"item_id": 1}
    with pytest.raises(HTTPException) as exc:
        asyncio.run(direct_call.call_route(_async_handler, item_id=404))
    assert exc.value.status_code == 404


def test_call_route_rejects_missing_or_unknown_arguments(session) -> None:
    with pytest.raises(TypeError):
        asyncio.run(direct_call.call_route(_async_handler))
    with pytest.raises(TypeError):
        asyncio.run(direct_call.call_route(_async_handler, item_id=1, other=2))
