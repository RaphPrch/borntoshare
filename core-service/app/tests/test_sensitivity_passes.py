import json
from types import SimpleNamespace

from app.services import sensitivity


class _Db:
    def __init__(self, current):
        self.current = current

    def execute(self, statement, params=None):
        return SimpleNamespace(scalar=lambda: self.current)


def _job(context=None):
    payload = {"action": sensitivity.ACTION, "payload": {"kind": "storage-root", "target": {"storage_root_id": 12},
                                                        "context": {"storage_root_id": 12, **(context or {})}}}
    return SimpleNamespace(id=157, job_type="SENSITIVITY_SCAN", identity_source_id=None, payload_json=json.dumps(payload))


def _setup(monkeypatch):
    created, published, marked = [], [], []

    class _Repo:
        def __init__(self, db):
            pass

        def create(self, *, data):
            created.append(data)
            return SimpleNamespace(id=900 + len(created))

    import app.data.repositories.provisioning_jobs_repo as repo_module
    import app.jobs.b2s_job_contracts.actors as actors

    monkeypatch.setattr(repo_module, "ProvisioningJobsRepo", _Repo)
    monkeypatch.setattr(actors, "publish_job", lambda job_type, job_id: published.append(job_id))
    monkeypatch.setattr(sensitivity, "incremental_params", lambda root_id: {"since": "2026-11-10", "cursor_path": "Data\\b.txt"})
    monkeypatch.setattr(sensitivity, "mark_requested", lambda db, root_id, job_id: marked.append((root_id, job_id)))
    return created, published, marked


def test_a_pass_with_files_left_queues_the_next(monkeypatch) -> None:
    created, published, marked = _setup(monkeypatch)
    new_id = sensitivity.continue_if_pending(_Db(157), _job(), {"incremental": {"complete": False, "pending": 64700}})
    assert new_id == 901 and published == [901] and marked == [(12, 901)]
    body = created[0]["payload_json"]["payload"]
    assert body["context"] == {"storage_root_id": 12, "pass": 2, "pending_before": 64700, "continues": 157}
    assert body["target"]["cursor_path"] == "Data\\b.txt"


def test_the_passes_stop(monkeypatch) -> None:
    created, _published, _marked = _setup(monkeypatch)
    left = {"incremental": {"complete": False, "pending": 500}}
    assert sensitivity.continue_if_pending(_Db(157), _job(), {"incremental": {"complete": True, "pending": 0}}) is None
    assert sensitivity.continue_if_pending(_Db(157), _job({"pending_before": 500}), left) is None  # no progress
    assert sensitivity.continue_if_pending(_Db(999), _job(), left) is None  # another scan of the folder took over
    assert sensitivity.continue_if_pending(_Db(157), _job({"pass": sensitivity.MAX_PASSES}), left) is None
    assert created == []
