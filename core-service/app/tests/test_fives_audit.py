"""The 5S module writes what it does to the files in the chained audit log of the core (internal route)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api import internal_fives


def _request(headers: dict[str, str]) -> Request:
    return Request({"type": "http", "headers": [(key.encode(), value.encode()) for key, value in headers.items()]})


def _capture(monkeypatch) -> list[dict]:
    written: list[dict] = []
    from app.services import activity_log

    monkeypatch.setattr(activity_log, "log_activity", lambda _db, **kwargs: written.append(kwargs) or {"ok": True})
    monkeypatch.setattr(internal_fives.lookups_repo, "storage_root",
                        lambda _db, root_id: SimpleNamespace(id=root_id, name="Finance", root_path="\\\\filer\\S\\Finance") if root_id == 7 else None)
    return written


def test_a_move_asked_by_a_person_is_written_with_the_person_and_the_folder(monkeypatch) -> None:
    written = _capture(monkeypatch)
    payload = internal_fives.FivesAuditPayload(action="storage_root.duplicates_quarantine_requested", storage_root_id=7, context={"count": 3})
    internal_fives.fives_audit(payload, _request({"x-identity-id": "12", "x-actor-display": "Jane", "x-roles": "user"}), db=None)
    event = written[0]
    assert event["actor_type"] == "user" and event["actor_id"] == 12 and event["actor_display"] == "Jane"
    assert event["target_type"] == "storage_root" and event["target_id"] == "7" and event["target_display"] == "\\\\filer\\S\\Finance"
    assert event["context_json"] == {"count": 3, "module": "fives"} and event["background"] is False


def test_the_scanner_writes_as_the_system(monkeypatch) -> None:
    written = _capture(monkeypatch)
    payload = internal_fives.FivesAuditPayload(action="storage_root.quarantine_purged", storage_root_id=7, outcome="failure")
    internal_fives.fives_audit(payload, _request({}), db=None)
    assert written[0]["actor_type"] == "system" and written[0]["actor_display"] == "Module 5S" and written[0]["outcome"] == "failure"


def test_only_known_actions_on_known_folders(monkeypatch) -> None:
    written = _capture(monkeypatch)
    with pytest.raises(HTTPException) as unknown:
        internal_fives.fives_audit(internal_fives.FivesAuditPayload(action="storage_root.deleted", storage_root_id=7), _request({}), db=None)
    assert unknown.value.status_code == 422
    with pytest.raises(HTTPException) as missing:
        internal_fives.fives_audit(internal_fives.FivesAuditPayload(action="storage_root.folder_archived", storage_root_id=99), _request({}), db=None)
    assert missing.value.status_code == 404 and written == []
