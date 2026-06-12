from __future__ import annotations

import asyncio

from app.services import identity_orchestration_service as svc


def test_search_identity_enriches_identity_id_from_batch_resolution(monkeypatch) -> None:
    async def _fake_resolve_searchable_snapshot(source_id: int | None):
        assert source_id == 5
        return 77, "ACTIVE"

    async def _fake_dal_get(path: str, timeout: int = 10):
        _ = timeout
        assert "/api/internal/directory-snapshots/runs/77/search" in path
        return {
            "items": [
                {
                    "principal_type": "user",
                    "external_id": "ad:user:1",
                    "dn": "CN=Alice,OU=Users,DC=example,DC=com",
                    "username": "alice",
                    "display_name": "Alice",
                    "email": "alice@example.com",
                    "is_active": True,
                },
                {
                    "principal_type": "group",
                    "external_id": None,
                    "dn": "CN=Finance,OU=Groups,DC=example,DC=com",
                    "username": None,
                    "display_name": "Finance",
                    "email": None,
                    "is_active": True,
                },
            ]
        }

    async def _fake_dal_post(path: str, payload: dict, timeout: int = 8):
        _ = timeout
        assert path == "/api/internal/identities/resolve-ad/batch"
        assert payload["identity_source_id"] == 5
        assert payload["create_if_missing"] is False
        assert len(payload["items"]) == 2
        return {
            "items": [
                {"found": True, "identity_id": "101"},
                {"found": False, "reason_code": "NOT_FOUND_IN_ACTIVE_SNAPSHOT"},
            ]
        }

    monkeypatch.setattr(svc, "_resolve_searchable_snapshot", _fake_resolve_searchable_snapshot)
    monkeypatch.setattr(svc, "dal_get", _fake_dal_get)
    monkeypatch.setattr(svc, "dal_post", _fake_dal_post)

    out = asyncio.run(svc.search_identity({"identity_source_id": 5, "query": "ali"}))

    assert out["snapshot_id"] == 77
    assert out["snapshot_status"] == "ACTIVE"
    assert len(out["items"]) == 2

    assert out["items"][0]["id"] == "ad:user:1"
    assert out["items"][0]["identity_id"] == 101
    assert out["items"][0]["identity_source_id"] == 5

    assert out["items"][1]["id"] == "CN=Finance,OU=Groups,DC=example,DC=com"
    assert out["items"][1]["identity_id"] is None
    assert out["groups"][0]["identity_id"] is None


def test_list_identity_overview_normalizes_identity_id_from_id_fallback(monkeypatch) -> None:
    async def _fake_dal_get(path: str, timeout: int = 10):
        _ = timeout
        assert path == "/api/identity"
        return [
            {"id": "42", "display_name": "Alice"},
            {"id": 7, "identity_id": 9, "display_name": "Bob"},
        ]

    monkeypatch.setattr(svc, "dal_get", _fake_dal_get)

    rows = asyncio.run(svc.list_identity_overview({}))

    assert rows[0]["id"] == "42"
    assert rows[0]["identity_id"] == 42

    assert rows[1]["id"] == 7
    assert rows[1]["identity_id"] == 9

