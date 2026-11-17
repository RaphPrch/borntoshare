"""/storage-roots/context: one server only (its page) and only the columns a page reads (fields=a,b)."""

from __future__ import annotations

from app.api import storage_roots as router
from app.services import dfs_links

ROWS = [
    {"storage_root_id": 1, "storage_root_name": "Finance", "storage_endpoint_id": 145, "zone_name": "Paris", "root_path": "\\\\f1\\Finance"},
    {"storage_root_id": 2, "storage_root_name": "RH", "storage_endpoint_id": 146, "zone_name": "Lyon", "root_path": "\\\\f2\\RH"},
]


class _Repo:
    def __init__(self, db) -> None:
        pass

    def list_context(self, zone_id=None):
        return [dict(row) for row in ROWS]


def _patch(monkeypatch) -> None:
    monkeypatch.setattr(router, "actor_from_request", lambda request: object())
    monkeypatch.setattr(router, "require_storage_roots_index", lambda db, actor: None)
    monkeypatch.setattr(router, "filter_storage_root_rows", lambda db, actor, rows: rows)
    monkeypatch.setattr(router, "StorageRootsViewsRepo", _Repo)
    monkeypatch.setattr(dfs_links, "dfs_paths_and_replicas", lambda db: ({}, {}))


def test_context_keeps_every_column_and_server_without_parameters(monkeypatch) -> None:
    _patch(monkeypatch)
    answer = router.list_storage_roots_context(request=None, db=None)
    assert [row["storage_root_id"] for row in answer["data"]] == [1, 2]
    assert answer["data"][0]["zone_name"] == "Paris"


def test_context_of_one_server_with_only_the_asked_columns(monkeypatch) -> None:
    _patch(monkeypatch)
    answer = router.list_storage_roots_context(request=None, storage_endpoint_id=146, fields="storage_root_id, storage_root_name,", db=None)
    assert answer["data"] == [{"storage_root_id": 2, "storage_root_name": "RH"}]
    assert answer["meta"]["count"] == 1
