from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api import storage_endpoints as api

ROWS = [
    {"id": 1, "name": "brest", "host": "DFS01.CORP.LOCAL", "zone_id": 1},
    {"id": 2, "name": "Paris", "host": "DFS01.CORP.LOCAL", "zone_id": 1},
    {"id": 3, "name": "FILER01", "host": "172.22.98.56", "zone_id": 2},
]


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows

    def scalar(self):
        return "CORP"


class _Db:
    def execute(self, statement, *_a, **_k):
        return _Result(ROWS)


def test_a_new_namespace_goes_in_the_zone_of_its_server():
    api._assert_zone_of_server(_Db(), "dfs01.corp.local", 1)
    api._assert_zone_of_server(_Db(), "DFS02.CORP.LOCAL", 2)
    with pytest.raises(HTTPException) as refused:
        api._assert_zone_of_server(_Db(), "DFS01", 2)
    assert refused.value.detail["code"] == "STORAGE_ENDPOINT_ZONE_OF_SERVER"


def test_siblings_are_the_other_endpoints_of_the_same_server():
    assert [row["id"] for row in api._same_server(_Db(), "dfs01.corp.local", exclude_id=1)] == [2]
