from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.core.action_registry import CapsuleActionError
from app.core import scope_guard


def test_scope_guard_allows_read_actions_in_read_mode(monkeypatch) -> None:
    monkeypatch.setattr(scope_guard.settings, "RUNNER_MAX_SCOPE", "read")
    scope_guard.ensure_action_scope_allowed("test_smb_ntlm")


def test_scope_guard_allows_storage_root_probe_in_read_mode(monkeypatch) -> None:
    monkeypatch.setattr(scope_guard.settings, "RUNNER_MAX_SCOPE", "read")
    scope_guard.ensure_action_scope_allowed("test_smb_root_access")


def test_scope_guard_denies_write_actions_in_read_mode(monkeypatch) -> None:
    monkeypatch.setattr(scope_guard.settings, "RUNNER_MAX_SCOPE", "read")
    with pytest.raises(CapsuleActionError) as exc:
        scope_guard.ensure_action_scope_allowed("ensure_ad_group")
    assert exc.value.error_code == "CAPSULE_SCOPE_DENIED"
    assert exc.value.retryable is False


def test_scope_guard_treats_unknown_actions_as_admin_and_denies_in_read_mode(monkeypatch) -> None:
    monkeypatch.setattr(scope_guard.settings, "RUNNER_MAX_SCOPE", "read")
    with pytest.raises(CapsuleActionError) as exc:
        scope_guard.ensure_action_scope_allowed("unknown_action")
    assert exc.value.error_code == "CAPSULE_SCOPE_DENIED"
