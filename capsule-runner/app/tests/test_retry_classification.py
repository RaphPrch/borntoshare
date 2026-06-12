from __future__ import annotations

from types import SimpleNamespace
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.core.action_registry import CapsuleActionError
from app.core import job_dispatcher as dispatcher
import app.shared.b2s_job_contracts.actors as actors


def test_non_retryable_error_is_acked_and_persisted(monkeypatch) -> None:
    post_calls: list[tuple[str, dict]] = []

    def _fake_dal_get(path: str):
        return {
            "id": 99,
            "status": "CREATED",
            "job_type": "SYNC",
            "action": "test_smb_ntlm",
            "payload_json": {
                "action": "test_smb_ntlm",
                "payload": {"host": "srv", "username": "u", "password": "p"},
            },
        }

    def _fake_dal_post(path: str, payload: dict):
        post_calls.append((path, payload))
        return {"ok": True}

    def _fake_execute(slug: str, inputs: dict, job_id=None):
        raise CapsuleActionError(
            error_code="CAPSULE_INVALID_PAYLOAD",
            message="bad payload",
            retryable=False,
        )

    monkeypatch.setattr(dispatcher, "dal_get", _fake_dal_get)
    monkeypatch.setattr(dispatcher, "dal_post", _fake_dal_post)
    monkeypatch.setattr(dispatcher, "execute_action", _fake_execute)
    monkeypatch.setattr(
        actors.CurrentMessage,
        "get_current_message",
        staticmethod(lambda: SimpleNamespace(options={"retries": 0, "max_retries": 5})),
    )

    # Must not raise: non-retryable is acknowledged after DAL fail write.
    actors.run_provisioning_job(99)

    assert post_calls[0][0] == "/api/internal/provisioning/jobs/99/start"
    assert post_calls[-1][0] == "/api/internal/provisioning/jobs/99/fail"
    assert post_calls[-1][1]["error_code"] == "CAPSULE_INVALID_PAYLOAD"


def test_action_resolution_failure_is_non_retryable_and_persisted(monkeypatch) -> None:
    post_calls: list[tuple[str, dict]] = []

    def _fake_dal_get(path: str):
        return {
            "id": 101,
            "status": "CREATED",
            "job_type": "UNKNOWN_ACTION_JOB",
            "action": "",
            "payload_json": {},
        }

    def _fake_dal_post(path: str, payload: dict):
        post_calls.append((path, payload))
        return {"ok": True}

    monkeypatch.setattr(dispatcher, "dal_get", _fake_dal_get)
    monkeypatch.setattr(dispatcher, "dal_post", _fake_dal_post)
    monkeypatch.setattr(
        actors.CurrentMessage,
        "get_current_message",
        staticmethod(lambda: SimpleNamespace(options={"retries": 0, "max_retries": 5})),
    )

    # Must not raise: unsupported job type is non-retryable and acked.
    actors.run_provisioning_job(101)

    assert post_calls[0][0] == "/api/internal/provisioning/jobs/101/start"
    assert post_calls[-1][0] == "/api/internal/provisioning/jobs/101/fail"
    assert post_calls[-1][1]["error_code"] == "CAPSULE_UNSUPPORTED_JOB_TYPE"


def test_directory_snapshot_success_completes_without_snapshot_side_effects(monkeypatch) -> None:
    post_calls: list[tuple[str, dict]] = []

    def _fake_dal_get(path: str):
        return {
            "id": 202,
            "status": "CREATED",
            "job_type": "DIRECTORY_SNAPSHOT",
            "action": "collect_directory_snapshot",
            "payload_json": {
                "action": "collect_directory_snapshot",
                "payload": {
                    "snapshot_id": 77,
                    "identity_source_id": 3,
                    "host": "dc01.corp.local",
                    "bind_dn": "CN=svc,DC=corp,DC=local",
                    "password": "secret",
                    "base_dn": "DC=corp,DC=local",
                },
            },
        }

    def _fake_dal_post(path: str, payload: dict):
        post_calls.append((path, payload))
        return {"ok": True}

    def _fake_execute(slug: str, inputs: dict, job_id=None):
        assert slug == "collect_directory_snapshot"
        assert int(inputs.get("snapshot_id") or 0) == 77
        return {
            "success": True,
            "message": "ok",
            "details": {
                "payload": {
                    "users": [{"external_id": "u1"}],
                    "groups": [{"external_id": "g1"}],
                    "memberships": [{"group_external_id": "g1", "member_external_id": "u1", "member_type": "user"}],
                }
            },
        }

    monkeypatch.setattr(dispatcher, "dal_get", _fake_dal_get)
    monkeypatch.setattr(dispatcher, "dal_post", _fake_dal_post)
    monkeypatch.setattr(dispatcher, "execute_action", _fake_execute)
    monkeypatch.setattr(
        actors.CurrentMessage,
        "get_current_message",
        staticmethod(lambda: SimpleNamespace(options={"retries": 0, "max_retries": 5})),
    )

    actors.run_provisioning_job(202)

    paths = [p for p, _ in post_calls]
    assert paths == [
        "/api/internal/provisioning/jobs/202/start",
        "/api/internal/provisioning/jobs/202/complete",
    ]


def test_directory_snapshot_failure_fails_without_snapshot_side_effects(monkeypatch) -> None:
    post_calls: list[tuple[str, dict]] = []

    def _fake_dal_get(path: str):
        return {
            "id": 203,
            "status": "CREATED",
            "job_type": "DIRECTORY_SNAPSHOT",
            "action": "collect_directory_snapshot",
            "payload_json": {
                "action": "collect_directory_snapshot",
                "payload": {
                    "snapshot_id": 88,
                    "identity_source_id": 4,
                    "host": "dc01.corp.local",
                    "bind_dn": "CN=svc,DC=corp,DC=local",
                    "password": "secret",
                    "base_dn": "DC=corp,DC=local",
                },
            },
        }

    def _fake_dal_post(path: str, payload: dict):
        post_calls.append((path, payload))
        return {"ok": True}

    def _fake_execute(slug: str, inputs: dict, job_id=None):
        raise CapsuleActionError(
            error_code="CAPSULE_EXECUTION_FAILED",
            message="ldap timeout",
            retryable=False,
        )

    monkeypatch.setattr(dispatcher, "dal_get", _fake_dal_get)
    monkeypatch.setattr(dispatcher, "dal_post", _fake_dal_post)
    monkeypatch.setattr(dispatcher, "execute_action", _fake_execute)
    monkeypatch.setattr(
        actors.CurrentMessage,
        "get_current_message",
        staticmethod(lambda: SimpleNamespace(options={"retries": 0, "max_retries": 5})),
    )

    actors.run_provisioning_job(203)

    paths = [p for p, _ in post_calls]
    assert paths == [
        "/api/internal/provisioning/jobs/203/start",
        "/api/internal/provisioning/jobs/203/fail",
    ]

    fail_payload = post_calls[-1][1]
    assert fail_payload["error_code"] == "CAPSULE_EXECUTION_FAILED"


def test_ad_group_ensure_success_uses_complete_not_complete_and_apply(monkeypatch) -> None:
    post_calls: list[tuple[str, dict]] = []

    def _fake_dal_get(path: str):
        return {
            "id": 204,
            "status": "CREATED",
            "job_type": "AD_GROUP_ENSURE",
            "action": "ensure_ad_group",
            "payload_json": {
                "action": "ensure_ad_group",
                "payload": {
                    "group_name": "B2S_TEST_GROUP",
                    "host": "dc01.corp.local",
                    "bind_dn": "CN=svc,DC=corp,DC=local",
                    "password": "secret",
                    "target_ou_dn": "OU=Groups,DC=corp,DC=local",
                },
            },
        }

    def _fake_dal_post(path: str, payload: dict):
        post_calls.append((path, payload))
        return {"ok": True}

    def _fake_execute(slug: str, inputs: dict, job_id=None):
        assert slug == "ensure_ad_group"
        return {
            "success": True,
            "message": "AD group created",
            "details": {"group_dn": "CN=B2S_TEST_GROUP,OU=Groups,DC=corp,DC=local"},
        }

    monkeypatch.setattr(dispatcher, "dal_get", _fake_dal_get)
    monkeypatch.setattr(dispatcher, "dal_post", _fake_dal_post)
    monkeypatch.setattr(dispatcher, "execute_action", _fake_execute)
    monkeypatch.setattr(
        actors.CurrentMessage,
        "get_current_message",
        staticmethod(lambda: SimpleNamespace(options={"retries": 0, "max_retries": 5})),
    )

    actors.run_provisioning_job(204)

    paths = [p for p, _ in post_calls]
    assert paths == [
        "/api/internal/provisioning/jobs/204/start",
        "/api/internal/provisioning/jobs/204/complete",
    ]
    assert all("complete-and-apply" not in p for p in paths)
