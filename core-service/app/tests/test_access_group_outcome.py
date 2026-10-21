from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.api import provisioning_internal


class _Repo:
    """In-memory StorageRootAccessProfilesRepo: one access group, records the outcomes it receives."""

    status = "PENDING"
    outcomes: list[dict] = []

    def __init__(self, db) -> None:
        pass

    def get(self, profile_id: int) -> dict:
        return {"id": profile_id, "status": _Repo.status}

    def record_outcome(self, profile_id: int, **kwargs) -> None:
        _Repo.outcomes.append({"id": profile_id, **kwargs})


@pytest.fixture()
def repo(monkeypatch):
    _Repo.status, _Repo.outcomes = "PENDING", []
    monkeypatch.setattr(provisioning_internal, "StorageRootAccessProfilesRepo", _Repo)
    return _Repo


def _job(job_type: str = "AD_ACCESS_GRANT") -> SimpleNamespace:
    return SimpleNamespace(storage_root_access_profile_id=56, job_type=job_type)


def test_a_successful_grant_stores_the_group_guid(repo) -> None:
    provisioning_internal._record_access_group_outcome(
        None,
        job_row=_job(),
        succeeded=True,
        result_json={"details": {"group_guid": "6f1c0a52-8f8e-4c51-9a3b-1f2d3c4b5a69", "group_dn": "CN=G,OU=Groups"}},
    )
    assert repo.outcomes == [{
        "id": 56, "succeeded": True, "group_external_id": "6f1c0a52-8f8e-4c51-9a3b-1f2d3c4b5a69", "error_message": None,
    }]


@pytest.mark.parametrize("status", ["SUCCEEDED", "ADOPTING"])
def test_a_failed_grant_keeps_a_working_group_and_a_pending_adoption(repo, status) -> None:
    repo.status = status
    provisioning_internal._record_access_group_outcome(
        None, job_row=_job(), succeeded=False, result_json={}, error_message="AD_PRINCIPAL_NOT_FOUND"
    )
    assert repo.outcomes == []


def test_a_failed_first_grant_marks_the_group_failed(repo) -> None:
    provisioning_internal._record_access_group_outcome(
        None, job_row=_job(), succeeded=False, result_json={}, error_message="AD_GROUP_NAME_CONFLICT"
    )
    assert repo.outcomes[0]["succeeded"] is False
    assert repo.outcomes[0]["error_message"] == "AD_GROUP_NAME_CONFLICT"


def test_other_jobs_are_ignored(repo) -> None:
    provisioning_internal._record_access_group_outcome(None, job_row=_job("SMB_PROBE"), succeeded=True, result_json={})
    assert repo.outcomes == []
