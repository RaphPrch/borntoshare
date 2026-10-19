from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import provisioning_internal as module
from app.api.provisioning_internal import EnsureAccessGroupPayload


def test_write_governance_event_accepts_empty_chain(monkeypatch) -> None:
    captured: dict = {}

    class _FakeResult:
        def mappings(self):
            return self

        def first(self):
            return None

    class _FakeDB:
        def execute(self, statement, params=None):
            sql = str(statement).lower()
            if "select event_hash from governance_events" in sql:
                return _FakeResult()
            if "insert into governance_events" in sql:
                captured.update(params or {})
                return _FakeResult()
            return _FakeResult()

    monkeypatch.setattr(module, "compute_event_hash", lambda prev_hash, payload: "h" * 64)
    monkeypatch.setattr(module, "scrub_secrets", lambda payload: payload)

    module._write_governance_event(
        _FakeDB(),
        event_type="profile_created",
        target_type="storage_root_access_profile",
        target_id=77,
        storage_root_access_profile_id=77,
        status_value="CREATED",
        payload_json={"k": "v"},
        actor_ip="127.0.0.1",
        user_agent="pytest",
    )

    assert captured.get("prev_hash") is None
    assert captured.get("event_hash") == "h" * 64


class _FakeAccessGroups:
    rows: dict[tuple[int, str], dict] = {}
    outcomes: list[tuple] = []

    def __init__(self, db):
        self.db = db

    def ensure(self, *, storage_root_id, access_level_code, group_name):
        key = (storage_root_id, access_level_code)
        if key in self.rows:
            return self.rows[key], False
        self.rows[key] = {"id": len(self.rows) + 1, "group_name": group_name, "status": "PENDING"}
        return self.rows[key], True

    def record_outcome(self, profile_id, **kwargs):
        self.outcomes.append((profile_id, kwargs))


class _FakeDB:
    def __init__(self, root_exists=True):
        self.root_exists = root_exists
        self.commits = 0

    def get(self, _model, _id):
        return object() if self.root_exists else None

    def commit(self):
        self.commits += 1


@pytest.fixture
def access_groups(monkeypatch):
    _FakeAccessGroups.rows = {}
    _FakeAccessGroups.outcomes = []
    monkeypatch.setattr(module, "StorageRootAccessProfilesRepo", _FakeAccessGroups)
    monkeypatch.setattr(module, "_write_governance_event", lambda *_a, **_k: None)
    return _FakeAccessGroups


def test_ensure_access_group_creates_once_then_keeps_the_first_name(access_groups) -> None:
    db = _FakeDB()
    first = module.ensure_storage_root_access_group(
        EnsureAccessGroupPayload(storage_root_id=7, access_level_code="write", group_name="B2S_FIN_WRITE"), db=db
    )
    again = module.ensure_storage_root_access_group(
        EnsureAccessGroupPayload(storage_root_id=7, access_level_code="WRITE", group_name="B2S_RENAMED_WRITE"), db=db
    )
    assert first["created"] is True and again["created"] is False
    assert again["data"]["group_name"] == "B2S_FIN_WRITE"
    assert db.commits == 2


def test_ensure_access_group_rejects_unknown_level_and_root(access_groups) -> None:
    with pytest.raises(HTTPException) as exc:
        module.ensure_storage_root_access_group(
            EnsureAccessGroupPayload(storage_root_id=7, access_level_code="OWNER", group_name="G"), db=_FakeDB()
        )
    assert exc.value.status_code == 422
    with pytest.raises(HTTPException) as exc:
        module.ensure_storage_root_access_group(
            EnsureAccessGroupPayload(storage_root_id=7, access_level_code="READ", group_name="G"), db=_FakeDB(root_exists=False)
        )
    assert exc.value.status_code == 404


def test_group_job_outcome_is_recorded_on_its_access_group(access_groups) -> None:
    job = SimpleNamespace(job_type="AD_GROUP_ENSURE", storage_root_access_profile_id=3)
    module._record_access_group_outcome(
        None, job_row=job, succeeded=True, result_json={"details": {"group_guid": "guid-1", "group_dn": "CN=G"}}
    )
    module._record_access_group_outcome(None, job_row=job, succeeded=False, result_json=None, error_message="boom")
    # Jobs not tied to an access group, or of another type, are ignored
    module._record_access_group_outcome(None, job_row=SimpleNamespace(job_type="ACL_APPLY", storage_root_access_profile_id=3), succeeded=True, result_json=None)
    module._record_access_group_outcome(None, job_row=SimpleNamespace(job_type="AD_GROUP_ENSURE", storage_root_access_profile_id=None), succeeded=True, result_json=None)

    assert access_groups.outcomes == [
        (3, {"succeeded": True, "group_external_id": "guid-1", "error_message": None}),
        (3, {"succeeded": False, "group_external_id": None, "error_message": "boom"}),
    ]
