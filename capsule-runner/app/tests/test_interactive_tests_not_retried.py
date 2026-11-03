from __future__ import annotations

import pytest

from app.core import job_dispatcher
from app.core.action_registry import CapsuleActionError


def _run(monkeypatch, ui_origin: str) -> list[str]:
    posted: list[str] = []
    job = {"status": "QUEUED", "action": "test_smb_ntlm",
           "payload_json": {"action": "test_smb_ntlm", "payload": {"target": {"host": "h"}, "context": {"ui_origin": ui_origin}}}}
    monkeypatch.setattr(job_dispatcher, "core_get", lambda _path: job)
    monkeypatch.setattr(job_dispatcher, "core_post", lambda path, _body: posted.append(path))
    monkeypatch.setattr(job_dispatcher, "ensure_action_scope_allowed", lambda _action: None)

    def timeout(*_args, **_kwargs):
        raise CapsuleActionError(error_code="CAPSULE_TIMEOUT", message="timeout", retryable=True, details={})

    monkeypatch.setattr(job_dispatcher, "execute_action", timeout)
    job_dispatcher.run_job(1, retries=0, max_retries=5)
    return posted


def test_a_test_started_from_a_screen_fails_at_once(monkeypatch) -> None:
    assert _run(monkeypatch, "admin")[-1].endswith("/fail")


def test_a_background_test_is_retried(monkeypatch) -> None:
    with pytest.raises(CapsuleActionError):
        _run(monkeypatch, "storage_root_create")
