import json

from app.services import job_board


class _Db:
    def execute(self, statement, params=None):
        names = {"storage_roots": [(1, "Angers")], "storage_endpoints": [(3, "FILER01")]}
        table = next((name for name in names if name in str(statement)), None)

        class _R:
            def all(self_inner):
                return names.get(table, [])

        return _R()

    def rollback(self):
        pass


def _probe(action, status, **extra):
    payload = {"payload": {"kind": "storage-root", "target": {"storage_root_id": 1, "host": "10.0.0.1"}, "context": {"storage_root_id": 1, "ui_origin": "sensitivity_scan"},
                           "options": {"timeout_sec": 60}, "auth": {"username": "u", "secret_ref": "sm://x", "password": "p"}}}
    return {"id": 9, "job_type": "SENSITIVITY_SCAN", "action": action, "status": status, "payload_json": json.dumps(payload), "metrics_json": '{"retries": 1}', **extra}


def test_a_failed_scan_is_summarised_and_can_be_retried() -> None:
    [job] = job_board.summarize(_Db(), [_probe("scan_smb_sensitivity", "FAILED", wait_seconds=2, run_seconds=40)])
    assert job["target"] == {"kind": "folder", "id": 1, "label": "Angers", "href": "/storage-roots?selected=1"}
    assert job["retryable"] and job["attempts"] == 2 and job["origin"] == "sensitivity_scan" and job["timeout_seconds"] == 60
    assert job["stuck"] is None


def test_stuck_rules() -> None:
    assert job_board.stuck_reason({"status": "QUEUED", "wait_seconds": 301}) == "queue"
    assert job_board.stuck_reason({"status": "QUEUED", "wait_seconds": 30}) is None
    running = _probe("scan_smb_sensitivity", "RUNNING", run_seconds=181)
    assert job_board.stuck_reason(running) == "running" and job_board.stuck_reason({**running, "run_seconds": 179}) is None


def test_jobs_tied_to_a_request_are_not_retried_here() -> None:
    row = {"id": 4, "job_type": "AD_ACCESS_GRANT", "action": "grant_ad_access", "status": "FAILED", "payload_json": '{"identity_source_id": 2, "group_name": "G"}'}
    [job] = job_board.summarize(_Db(), [row])
    assert not job["retryable"] and job["retry_elsewhere"] == "Access requests" and job["target"]["kind"] == "directory"


def test_secrets_are_hidden_but_references_stay() -> None:
    shown = job_board.redact(job_board.envelope(_probe("x", "FAILED")))
    assert shown["auth"] == {"username": "u", "secret_ref": "sm://x", "password": "••••"}
