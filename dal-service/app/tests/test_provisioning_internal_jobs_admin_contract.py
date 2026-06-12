from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers import provisioning_internal as module


class _Rows:
    def __init__(self, rows: list[dict] | None = None):
        self._rows = rows or []

    def mappings(self):
        return self

    def all(self):
        return list(self._rows)


class _FakeDB:
    def __init__(self, rows: list[dict] | None = None):
        self.rows = rows or []
        self.last_sql: str = ""
        self.last_params: dict = {}
        self.commit_calls = 0

    def execute(self, statement, params=None):
        self.last_sql = str(statement)
        self.last_params = dict(params or {})
        return _Rows(self.rows)

    def commit(self):
        self.commit_calls += 1


def test_list_jobs_normalizes_status_filters_and_clamps_limit() -> None:
    db = _FakeDB(
        rows=[
            {
                "id": 81,
                "status": "QUEUED",
                "job_type": "AD_GROUP_ENSURE",
                "watchdog_republish_count": 0,
            }
        ]
    )

    out = module.list_provisioning_jobs(
        status="queued,canceled",
        active_only=True,
        limit=5000,
        db=db,
    )

    assert len(out) == 1
    assert out[0]["id"] == 81
    assert db.last_params["lim"] == 1000
    assert db.last_params["status_0"] == "QUEUED"
    assert db.last_params["status_1"] == "CANCELLED"
    assert "IN ('CREATED','QUEUED','RUNNING','RETRYING')" in db.last_sql


def test_list_jobs_supports_csv_job_type_filter() -> None:
    db = _FakeDB(rows=[])

    _ = module.list_provisioning_jobs(
        job_type="AD_GROUP_ENSURE,ACL_APPLY",
        db=db,
    )

    assert db.last_params["job_type_0"] == "AD_GROUP_ENSURE"
    assert db.last_params["job_type_1"] == "ACL_APPLY"
    assert "UPPER(COALESCE(pj.job_type, '')) IN (:job_type_0, :job_type_1)" in db.last_sql


def test_cancel_job_rejects_terminal_succeeded(monkeypatch) -> None:
    class _Repo:
        def __init__(self, _db):
            pass

        @staticmethod
        def get_by_id(_job_id: int):
            return SimpleNamespace(id=9, status="SUCCEEDED")

        @staticmethod
        def to_dict(obj):
            return {"id": int(getattr(obj, "id", 0)), "status": str(getattr(obj, "status", ""))}

    monkeypatch.setattr(module, "ProvisioningJobsRepo", _Repo)

    with pytest.raises(HTTPException) as exc:
        module.cancel_provisioning_job(
            9,
            module.JobCancelPayload(correlation_id="corr_cancel_01"),
            db=_FakeDB(),
        )

    assert exc.value.status_code == 409


def test_cancel_job_is_idempotent_when_already_cancelled(monkeypatch) -> None:
    class _Repo:
        update_calls = 0

        def __init__(self, _db):
            pass

        @staticmethod
        def get_by_id(_job_id: int):
            return SimpleNamespace(id=10, status="CANCELLED", metrics_json={})

        def update(self, *, obj, updates: dict):  # pragma: no cover - guard
            _ = obj, updates
            _Repo.update_calls += 1
            raise AssertionError("update must not be called for already-cancelled job")

        @staticmethod
        def to_dict(obj):
            return {"id": int(getattr(obj, "id", 0)), "status": str(getattr(obj, "status", ""))}

    monkeypatch.setattr(module, "ProvisioningJobsRepo", _Repo)

    out = module.cancel_provisioning_job(
        10,
        module.JobCancelPayload(correlation_id="corr_cancel_02"),
        db=_FakeDB(),
    )

    assert out["status"] == "CANCELLED"
    assert _Repo.update_calls == 0


def test_cancel_job_updates_status_metrics_and_error_payload(monkeypatch) -> None:
    fixed_now = datetime(2026, 3, 27, 10, 30, 0)
    db = _FakeDB()
    event_calls: list[dict] = []

    class _Repo:
        last_updates: dict | None = None

        def __init__(self, _db):
            pass

        @staticmethod
        def get_by_id(_job_id: int):
            return SimpleNamespace(
                id=11,
                status="QUEUED",
                job_type="AD_GROUP_ENSURE",
                identity_source_id=5,
                result_json={},
                metrics_json={"retry": 1},
            )

        def update(self, *, obj, updates: dict):
            _Repo.last_updates = dict(updates)
            for k, v in updates.items():
                setattr(obj, k, v)
            return obj

        @staticmethod
        def to_dict(obj):
            return {
                "id": int(getattr(obj, "id", 0)),
                "status": str(getattr(obj, "status", "")),
                "error_code": getattr(obj, "error_code", None),
                "error_message": getattr(obj, "error_message", None),
                "metrics_json": dict(getattr(obj, "metrics_json", {}) or {}),
            }

    monkeypatch.setattr(module, "ProvisioningJobsRepo", _Repo)
    monkeypatch.setattr(module, "_utcnow_naive", lambda: fixed_now)
    monkeypatch.setattr(module, "_persist_identity_source_probe_result", lambda *_a, **_k: None)
    monkeypatch.setattr(module, "_write_governance_event", lambda *_a, **k: event_calls.append(dict(k)))

    out = module.cancel_provisioning_job(
        11,
        module.JobCancelPayload(
            correlation_id="corr_cancel_03",
            reason="Stopped by operator",
            requested_by="admin-1",
            source="ui",
        ),
        db=db,
    )

    assert out["status"] == "CANCELLED"
    assert out["error_code"] == "JOB_CANCELLED"
    assert out["error_message"] == "Stopped by operator"
    assert db.commit_calls == 1
    assert isinstance(_Repo.last_updates, dict)
    cancel_meta = (_Repo.last_updates or {}).get("metrics_json", {}).get("cancel", {})
    assert cancel_meta.get("correlation_id") == "corr_cancel_03"
    assert cancel_meta.get("requested_by") == "admin-1"
    assert len(event_calls) == 1


def test_watchdog_mark_increments_republish_counter(monkeypatch) -> None:
    fixed_now = datetime(2026, 3, 27, 11, 0, 0)
    db = _FakeDB()
    write_events = {"count": 0}

    class _Repo:
        update_calls = 0

        def __init__(self, _db):
            pass

        @staticmethod
        def get_by_id(_job_id: int):
            return SimpleNamespace(id=12, status="QUEUED", metrics_json={})

        def update(self, *, obj, updates: dict):
            _Repo.update_calls += 1
            for k, v in updates.items():
                setattr(obj, k, v)
            return obj

        @staticmethod
        def to_dict(obj):
            return {
                "id": int(getattr(obj, "id", 0)),
                "status": str(getattr(obj, "status", "")),
                "metrics_json": dict(getattr(obj, "metrics_json", {}) or {}),
            }

    monkeypatch.setattr(module, "ProvisioningJobsRepo", _Repo)
    monkeypatch.setattr(module, "_utcnow_naive", lambda: fixed_now)
    monkeypatch.setattr(module, "_write_governance_event", lambda *_a, **_k: write_events.__setitem__("count", write_events["count"] + 1))

    out = module.mark_watchdog_republish(
        12,
        module.JobWatchdogRepublishPayload(correlation_id="corr_watchdog_01", reason="queued_timeout_300s"),
        db=db,
    )

    assert out["status"] == "QUEUED"
    assert out["metrics_json"]["watchdog_republish_count"] == 1
    assert out["metrics_json"]["last_republish_correlation_id"] == "corr_watchdog_01"
    assert _Repo.update_calls == 1
    assert db.commit_calls == 1
    assert write_events["count"] == 1


def test_watchdog_mark_is_noop_when_not_queued(monkeypatch) -> None:
    db = _FakeDB()

    class _Repo:
        update_calls = 0

        def __init__(self, _db):
            pass

        @staticmethod
        def get_by_id(_job_id: int):
            return SimpleNamespace(id=13, status="RUNNING", metrics_json={"watchdog_republish_count": 2})

        def update(self, *, obj, updates: dict):  # pragma: no cover - guard
            _ = obj, updates
            _Repo.update_calls += 1
            raise AssertionError("update must not be called when status is not QUEUED")

        @staticmethod
        def to_dict(obj):
            return {
                "id": int(getattr(obj, "id", 0)),
                "status": str(getattr(obj, "status", "")),
                "metrics_json": dict(getattr(obj, "metrics_json", {}) or {}),
            }

    monkeypatch.setattr(module, "ProvisioningJobsRepo", _Repo)

    out = module.mark_watchdog_republish(
        13,
        module.JobWatchdogRepublishPayload(correlation_id="corr_watchdog_02", reason="n/a"),
        db=db,
    )

    assert out["status"] == "RUNNING"
    assert out["metrics_json"]["watchdog_republish_count"] == 2
    assert _Repo.update_calls == 0
    assert db.commit_calls == 0


def test_complete_and_fail_return_unchanged_when_job_is_cancelled(monkeypatch) -> None:
    class _Repo:
        update_calls = 0

        def __init__(self, _db):
            pass

        @staticmethod
        def get_by_id(_job_id: int):
            return SimpleNamespace(id=14, status="CANCELLED", metrics_json={})

        def update(self, *, obj, updates: dict):  # pragma: no cover - guard
            _ = obj, updates
            _Repo.update_calls += 1
            raise AssertionError("update must not be called for cancelled jobs")

        @staticmethod
        def to_dict(obj):
            return {"id": int(getattr(obj, "id", 0)), "status": str(getattr(obj, "status", ""))}

    monkeypatch.setattr(module, "ProvisioningJobsRepo", _Repo)

    completed = module.complete_provisioning_job(
        14,
        module.JobCompletePayload(correlation_id="corr_complete_01"),
        db=_FakeDB(),
    )
    failed = module.fail_provisioning_job(
        14,
        module.JobFailPayload(correlation_id="corr_fail_01", error_code="IGNORED"),
        db=_FakeDB(),
    )

    assert completed["status"] == "CANCELLED"
    assert failed["status"] == "CANCELLED"
    assert _Repo.update_calls == 0


def test_complete_job_writes_governance_event(monkeypatch) -> None:
    event_calls: list[dict] = []

    class _Repo:
        update_calls = 0

        def __init__(self, _db):
            pass

        @staticmethod
        def get_by_id(_job_id: int):
            return SimpleNamespace(
                id=21,
                status="RUNNING",
                action="ensure_ad_group",
                job_type="AD_GROUP_ENSURE",
                storage_root_access_profile_id=77,
                identity_source_id=9,
                result_json={},
                metrics_json={},
            )

        def update(self, *, obj, updates: dict):
            _Repo.update_calls += 1
            merged = dict(vars(obj))
            merged.update(updates)
            return SimpleNamespace(**merged)

        @staticmethod
        def to_dict(obj):
            return {
                "id": int(getattr(obj, "id", 0)),
                "status": str(getattr(obj, "status", "")),
                "storage_root_access_profile_id": int(getattr(obj, "storage_root_access_profile_id", 0) or 0) or None,
            }

    monkeypatch.setattr(module, "ProvisioningJobsRepo", _Repo)
    monkeypatch.setattr(module, "_persist_identity_source_probe_result", lambda *_a, **_k: None)
    monkeypatch.setattr(module, "_write_governance_event", lambda *_a, **kwargs: event_calls.append(dict(kwargs)))

    out = module.complete_provisioning_job(
        21,
        module.JobCompletePayload(
            action="ensure_ad_group",
            result_json={"ok": True},
            metrics_json={"retries": 0},
            correlation_id="corr_complete_evt_01",
        ),
        db=_FakeDB(),
    )

    assert out["status"] == "SUCCEEDED"
    assert len(event_calls) == 1
    assert event_calls[0]["event_type"] == "provisioning_job_succeeded"
    assert event_calls[0]["status_value"] == "SUCCEEDED"


def test_fail_job_writes_governance_event(monkeypatch) -> None:
    event_calls: list[dict] = []

    class _Repo:
        update_calls = 0

        def __init__(self, _db):
            pass

        @staticmethod
        def get_by_id(_job_id: int):
            return SimpleNamespace(
                id=22,
                status="RUNNING",
                action="ensure_ad_group",
                job_type="AD_GROUP_ENSURE",
                storage_root_access_profile_id=88,
                identity_source_id=9,
                result_json={},
                metrics_json={},
            )

        def update(self, *, obj, updates: dict):
            _Repo.update_calls += 1
            merged = dict(vars(obj))
            merged.update(updates)
            return SimpleNamespace(**merged)

        @staticmethod
        def to_dict(obj):
            return {
                "id": int(getattr(obj, "id", 0)),
                "status": str(getattr(obj, "status", "")),
                "storage_root_access_profile_id": int(getattr(obj, "storage_root_access_profile_id", 0) or 0) or None,
            }

    monkeypatch.setattr(module, "ProvisioningJobsRepo", _Repo)
    monkeypatch.setattr(module, "_persist_identity_source_probe_result", lambda *_a, **_k: None)
    monkeypatch.setattr(module, "_write_governance_event", lambda *_a, **kwargs: event_calls.append(dict(kwargs)))

    out = module.fail_provisioning_job(
        22,
        module.JobFailPayload(
            action="ensure_ad_group",
            error_code="CAPSULE_FAIL",
            error_message="boom",
            correlation_id="corr_fail_evt_01",
        ),
        db=_FakeDB(),
    )

    assert out["status"] == "FAILED"
    assert len(event_calls) == 1
    assert event_calls[0]["event_type"] == "provisioning_job_failed"
    assert event_calls[0]["status_value"] == "FAILED"
