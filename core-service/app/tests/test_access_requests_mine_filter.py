from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.api import access_requests as router


def test_mine_keeps_only_the_requests_of_the_caller(monkeypatch) -> None:
    rows = [
        {"request_id": 1, "requester_identity_id": 7, "storage_root_id": 10},
        {"request_id": 2, "requester_identity_id": 9, "storage_root_id": 11},
        {"request_id": 3, "requester_identity_id": 7, "storage_root_id": 12},
    ]

    class _FakeViewsRepo:
        def __init__(self, _db) -> None:
            pass

        def list(self, **_kwargs):
            return list(rows)

    monkeypatch.setattr(router, "AccessRequestsViewsRepo", _FakeViewsRepo)
    monkeypatch.setattr(router, "actor_from_request", lambda _request: SimpleNamespace(identity_id=7))
    monkeypatch.setattr(router, "filter_access_request_rows", lambda _db, _actor, items: items)

    mine = router.list_access_requests(request=None, mine=1, db=None)
    every = router.list_access_requests(request=None, db=None)

    assert [row["request_id"] for row in mine["data"]] == [1, 3]
    assert len(every["data"]) == 3
