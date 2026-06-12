from __future__ import annotations

import asyncio

from app.services import identity_orchestration_service as svc


def test_search_identity_includes_group_and_excludes_ou_from_items(monkeypatch) -> None:
    async def _fake_resolve_searchable_snapshot(source_id: int | None):
        assert source_id == 12
        return 55, "ACTIVE"

    async def _fake_dal_get(path: str, timeout: int = 10):
        _ = timeout
        assert "/api/internal/directory-snapshots/runs/55/search" in path
        return {
            "items": [
                {
                    "principal_type": "user",
                    "external_id": "ad:user:john",
                    "dn": "CN=John,OU=Users,DC=corp,DC=local",
                    "username": "john",
                    "display_name": "John",
                    "email": "john@corp.local",
                    "is_active": True,
                },
                {
                    "principal_type": "group",
                    "external_id": "ad:group:finance",
                    "dn": "CN=Finance,OU=Groups,DC=corp,DC=local",
                    "username": "finance",
                    "display_name": "Finance",
                    "email": None,
                    "is_active": True,
                },
                {
                    "principal_type": "ou",
                    "external_id": "ou:users",
                    "dn": "OU=Users,DC=corp,DC=local",
                    "username": None,
                    "display_name": "Users OU",
                    "email": None,
                    "is_active": True,
                },
            ]
        }

    async def _fake_dal_post(path: str, payload: dict, timeout: int = 8):
        _ = timeout
        assert path == "/api/internal/identities/resolve-ad/batch"
        assert payload.get("identity_source_id") == 12
        assert len(payload.get("items") or []) == 3
        return {
            "items": [
                {"found": True, "identity_id": "701"},
                {"found": True, "identity_id": "702"},
                {"found": False, "reason_code": "NOT_FOUND_IN_ACTIVE_SNAPSHOT"},
            ]
        }

    monkeypatch.setattr(svc, "_resolve_searchable_snapshot", _fake_resolve_searchable_snapshot)
    monkeypatch.setattr(svc, "dal_get", _fake_dal_get)
    monkeypatch.setattr(svc, "dal_post", _fake_dal_post)

    out = asyncio.run(svc.search_identity({"identity_source_id": 12, "query": "*"}))

    assert out["snapshot_id"] == 55
    assert len(out["items"]) == 3
    assert [str(item.get("type") or "") for item in out["items"]] == ["user", "group", "ou"]

    assert len(out["users"]) == 1
    assert out["users"][0]["identity_id"] == 701

    assert len(out["groups"]) == 1
    assert out["groups"][0]["identity_id"] == 702

    assert len(out["ous"]) == 1

