"""History of the data indicators: one point a day, counted with the rules of the express search."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import insights as routes
from app.core.db import get_db
from app.services import folder_query
from app.services.indicator_history import indicators, snapshot_rows

ROWS = [
    {"storage_root_id": 1, "zone_id": 3, "content_size_bytes": 100, "cold_1y_bytes": 60, "guardians_count": 1, "password_files": 0,
     "key_files": 1, "quota_used_percent": 90, "quota_warn_percent": 85, "open_alerts_count": 2, "dup_wasted_bytes": 5},
    {"storage_root_id": 2, "zone_id": 3, "content_size_bytes": None, "estimated_size_bytes": None, "guardians_count": 0, "open_alerts_count": 0},
    {"storage_root_id": 3, "zone_id": 4, "estimated_size_bytes": 40, "guardians_count": 2, "password_files": 2, "shared_dup_bytes": 7,
     "open_alerts_count": 1},
]


def test_a_point_is_what_the_lists_showed_that_day() -> None:
    values = indicators(ROWS)
    # The same rules as « See » in Storage Roots
    assert values["measured"] == len(ROWS) - sum(folder_query.STATES["non-mesure"](row) for row in ROWS) == 2
    assert values["with_guardian"] == 2
    assert values["secret_folders"] == sum(folder_query.STATES["secret"](row) for row in ROWS) == 2
    assert values["quota_full"] == 1 and values["alert_folders"] == 2 and values["open_alerts"] == 3
    assert values["volume_bytes"] == 140 and values["cold_bytes"] == 60 and values["dup_bytes"] == 12
    # A part not read that day is unknown (None), never zero
    assert values["exposure"] is None and values["servers"] is None


def test_the_platform_and_each_zone() -> None:
    exposure = ({"governed": 2, "open_read": 1}, {3: {"governed": 2}, 4: {"open_read": 1}})
    servers = ({"available": 3, "degraded": 1}, {3: {"available": 2}, 4: {"available": 1, "degraded": 1}, 9: {"unknown": 1}})
    scopes = {(kind, scope): values for kind, scope, values in snapshot_rows(ROWS, exposure, servers)}
    assert set(scopes) == {("platform", 0), ("zone", 3), ("zone", 4), ("zone", 9)}
    assert scopes[("platform", 0)]["folders"] == 3 and scopes[("platform", 0)]["exposure"]["governed"] == 2
    assert scopes[("zone", 3)]["folders"] == 2 and scopes[("zone", 4)]["servers"]["degraded"] == 1
    # A zone with servers and no governed folder yet: its servers count, its folders are zero (known: there are none)
    assert scopes[("zone", 9)]["folders"] == 0 and scopes[("zone", 9)]["servers"]["unknown"] == 1
    # The exposure could not be read: unknown everywhere, the rest of the day is kept
    assert all(values["exposure"] is None for _k, _s, values in snapshot_rows(ROWS, None, servers))


def test_only_administrators_read_the_history(monkeypatch) -> None:
    monkeypatch.setattr("app.services.indicator_history.history", lambda db, days, zone_id: [{"day": "2026-11-26", "folders": 3}])
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_db] = lambda: None
    client = TestClient(app)
    for roles in ("guardian", "user"):
        assert client.get("/insights/history", headers={"x-identity-id": "7", "x-roles": roles}).status_code == 403
    response = client.get("/insights/history?days=30", headers={"x-identity-id": "1", "x-roles": "platform_admin"})
    assert response.status_code == 200 and response.json()["data"][0]["folders"] == 3
    assert client.get("/insights/history?days=999", headers={"x-identity-id": "1", "x-roles": "admin"}).status_code == 422
