from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import storage_endpoints
from app.services import dfs_links

DECLARED = SimpleNamespace(name="brest", endpoint_type="dfs", path="\\\\corp.local\\brest")


class _Db:
    def query(self, _model):
        return SimpleNamespace(filter=lambda *_: SimpleNamespace(all=lambda: [DECLARED]))


@pytest.fixture(autouse=True)
def _snapshot(monkeypatch) -> None:
    monkeypatch.setattr(dfs_links, "snapshot", lambda endpoint: {"path": endpoint.path})


def test_the_same_namespace_in_other_case_is_refused() -> None:
    with pytest.raises(HTTPException) as refused:
        storage_endpoints._assert_namespace_free(_Db(), "\\\\CORP.LOCAL\\brest\\")
    assert refused.value.status_code == 409 and refused.value.detail["code"] == "DFS_NAMESPACE_TAKEN"


def test_another_namespace_is_free() -> None:
    storage_endpoints._assert_namespace_free(_Db(), "\\\\corp.local\\lorient")


def test_a_namespace_not_read_is_refused() -> None:
    with pytest.raises(HTTPException) as refused:
        storage_endpoints._assert_namespace_free(_Db(), "corp.local\\brest")
    assert refused.value.detail["code"] == "DFS_NAMESPACE_PATH_INVALID"
