from __future__ import annotations

import asyncio

from fastapi import HTTPException

from app.services import features as policies_features
from app.services import policies


class _Db:
    def __init__(self):
        self.updates = []

    def execute(self, statement, params=None):
        self.updates.append(params)

    def commit(self):
        pass


def test_a_task_refused_by_the_queue_is_tried_again_next_run(monkeypatch):
    async def submit(payload):
        if payload["target"]["storage_root_id"] == 2:
            raise HTTPException(status_code=409, detail="No account")
        return {"job_id": "7"}

    import app.services.probe_service as probe_service
    import app.services.sensitivity as sensitivity

    monkeypatch.setattr(probe_service, "submit_probe_run", submit)
    monkeypatch.setattr(sensitivity, "mark_requested", lambda *a, **k: None)
    monkeypatch.setattr(policies_features, "enabled", lambda db, feature: True)
    db = _Db()
    jobs = [
        {"policy_id": 5, "storage_root_id": 1, "kind": "check"},
        {"policy_id": 5, "storage_root_id": 1, "kind": "sensitivity"},
        {"policy_id": 5, "storage_root_id": 2, "kind": "sensitivity"},
    ]
    done = asyncio.run(policies.dispatch_jobs(db, jobs))
    assert done == {"check": 1, "measure": 0, "sensitivity": 1, "failed": 1}
    # Only folder 1 gets its date: folder 2 stays due
    assert [(row["policy"], row["root"]) for row in db.updates[-1]] == [(5, 1)]


def test_no_sensitivity_scan_is_sent_while_the_5s_module_is_off(monkeypatch):
    sent = []

    async def submit(payload):
        sent.append(payload["protocol"])
        return {"job_id": "7"}

    import app.services.probe_service as probe_service

    monkeypatch.setattr(probe_service, "submit_probe_run", submit)
    monkeypatch.setattr(policies_features, "enabled", lambda db, feature: False)
    jobs = [
        {"policy_id": 5, "storage_root_id": 1, "kind": "check"},
        {"policy_id": 5, "storage_root_id": 1, "kind": "sensitivity"},
    ]
    done = asyncio.run(policies.dispatch_jobs(_Db(), jobs))
    assert sent == ["smb"]
    assert done == {"check": 1, "measure": 0, "sensitivity": 0, "failed": 0}
