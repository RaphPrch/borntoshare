"""Schedules › File servers (task « dfs_read »): every server tested, its folders on demand, the DFS namespaces read."""
from __future__ import annotations

import asyncio
import json

from app.services import dfs_refresh, file_server_health, probe_service


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self._rows

    def scalar(self):
        return self._rows


class _Db:
    def __init__(self, options):
        self.options = options

    def execute(self, statement, params=None):
        sql = str(statement)
        if "options_json" in sql:
            return _Rows(json.dumps(self.options))
        if "FROM storage_endpoints" in sql:
            return _Rows([{"id": 1, "name": "FILER01", "host": "filer01", "port": 445, "bind_dn": "CORP\\svc", "bind_password_ref": "ref"},
                          {"id": 2, "name": "NOACC", "host": "x", "port": 445, "bind_dn": "", "bind_password_ref": None}])
        if "FROM storage_roots" in sql:
            return _Rows([{"id": 10, "name": "DATA"}, {"id": 11, "name": "RH"}])
        raise AssertionError(sql)


def _run(monkeypatch, options):
    sent: list[dict] = []

    async def _submit(payload):
        sent.append(payload)
        return {"job_id": len(sent)}

    async def _dfs(db, *, trigger):
        return {"status": "success", "message": "17 espace(s) de noms relu(s)"}

    monkeypatch.setattr(probe_service, "submit_probe_run", _submit)
    monkeypatch.setattr(dfs_refresh, "run_dfs_read", _dfs)
    return asyncio.run(file_server_health.run_file_servers(_Db(options), trigger="schedule")), sent


def test_servers_only_by_default_with_the_dfs_namespaces(monkeypatch) -> None:
    result, sent = _run(monkeypatch, {})
    assert [p["kind"] for p in sent] == ["storage-endpoint"]
    assert result["servers"] == 1 and result["skipped_without_account"] == 1 and result["folders"] == 0
    assert result["status"] == "success" and "espace(s) de noms" in result["message"]


def test_their_folders_too_and_no_dfs(monkeypatch) -> None:
    result, sent = _run(monkeypatch, {"folders": True, "dfs": False})
    assert [p["kind"] for p in sent] == ["storage-endpoint", "storage-root", "storage-root"]
    assert result["folders"] == 2 and "dfs" not in result
