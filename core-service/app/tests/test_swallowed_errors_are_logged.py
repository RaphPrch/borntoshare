"""An error that degrades a result (full scan instead of incremental, no 5S measure in the Job Center…) is logged
with its event code: the degraded result stays, the reason is never lost."""
from __future__ import annotations

import logging

import httpx

from app.services import group_ou_check, modules, sensitivity


class _FailingSession:
    def execute(self, *_a, **_kw):
        raise RuntimeError("lost connection to MariaDB")

    def close(self):
        pass


def test_unreadable_incremental_state_means_a_full_scan_and_a_warning(monkeypatch, caplog) -> None:
    import app.core.db as core_db

    monkeypatch.setattr(core_db, "SessionLocal", lambda: _FailingSession())
    with caplog.at_level(logging.WARNING):
        assert sensitivity.incremental_params(5) == {}
    assert any(r.getMessage() == "SENSITIVITY_INCREMENTAL_STATE_UNREADABLE" for r in caplog.records)


def test_runs_of_the_module_unavailable_are_logged(monkeypatch, caplog) -> None:
    monkeypatch.setattr(modules, "fives_url", lambda: "http://fives-service:8000")
    monkeypatch.setattr(modules, "fives_installed", lambda: True)

    def refused(*_a, **_kw):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(modules.httpx, "get", refused)
    with caplog.at_level(logging.WARNING):
        assert modules.list_runs() == []
        assert modules.folder_paths(3) == []
    names = {r.getMessage() for r in caplog.records}
    assert {"FIVES_RUNS_UNAVAILABLE", "FIVES_FOLDER_PATHS_UNAVAILABLE"} <= names


def test_a_folder_whose_context_fails_is_named_in_the_log(monkeypatch, caplog) -> None:
    import app.api.provisioning_internal as provisioning_internal

    class _Rows:
        def all(self):
            return [(11,)]

    class _DB:
        def execute(self, *_a, **_kw):
            return _Rows()

    def broken(_root_id, _db):
        raise RuntimeError("zone missing")

    monkeypatch.setattr(provisioning_internal, "get_storage_root_provisioning_context", broken)
    with caplog.at_level(logging.WARNING):
        assert group_ou_check.ous_in_use(_DB()) == {}
    assert any(r.getMessage() == "GROUP_OU_CONTEXT_UNREADABLE" and r.storage_root_id == 11 for r in caplog.records)
