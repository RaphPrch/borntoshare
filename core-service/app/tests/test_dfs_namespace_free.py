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


def test_dfs_folder_names() -> None:
    from app.services.windows_names import dfs_folder_error

    assert dfs_folder_error("Corporate\\Finance") is None
    for bad in ("", "a\\..\\b", "Fin:ance", "Fin|ance", "a\\\\b", "Corporate\\CON", "Finance."):
        assert dfs_folder_error(bad), bad


def test_a_share_counts_the_folders_managed_in_it() -> None:
    from app.api.storage_roots import _discovered_item, _normalize_root_path

    endpoint = SimpleNamespace(id=90, name="FILER01")
    managed = {_normalize_root_path(p) for p in ("\\\\fs\\Finance\\A", "\\\\fs\\Finance\\A\\B", "\\\\fs\\FinanceX\\C")}
    item = _discovered_item(endpoint, {"root_path": "\\\\fs\\Finance", "name": "Finance"}, managed)
    assert item["managed"] is False and item["managed_below"] == 2


def test_a_refused_delegation_is_remembered_until_a_change_goes_through() -> None:
    endpoint = SimpleNamespace(capabilities={"dfs_snapshot": {"path": "x"}}, bind_dn="CORP\\svc")
    storage_endpoints._remember_dfs_delegation(endpoint, denied=True)
    assert endpoint.capabilities["dfs_manage_denied"]["account"] == "CORP\\svc"
    storage_endpoints._remember_dfs_delegation(endpoint, denied=False)
    assert "dfs_manage_denied" not in endpoint.capabilities and endpoint.capabilities["dfs_snapshot"] == {"path": "x"}
