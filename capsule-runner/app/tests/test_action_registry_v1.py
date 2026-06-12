from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.core import action_registry as registry
from app.middleware.resolve_secrets import CapsuleSecretResolutionError


def test_unknown_action_is_rejected() -> None:
    with pytest.raises(registry.CapsuleActionError) as exc:
        registry.execute_action("not_allowed", {}, job_id=1)
    assert exc.value.error_code == "CAPSULE_INVALID_ACTION"


def test_invalid_payload_is_rejected(monkeypatch) -> None:
    with pytest.raises(registry.CapsuleActionError) as exc:
        registry.execute_action("test_smb_ntlm", {"host": "srv"}, job_id=2)
    assert exc.value.error_code == "CAPSULE_INVALID_PAYLOAD"
    assert exc.value.retryable is False


def test_secret_resolution_failure_maps_error(monkeypatch) -> None:
    def _boom(payload, fields):
        raise CapsuleSecretResolutionError(
            error_code="SECRET_NOT_FOUND",
            message="missing",
            secret_ref="sm://storage-endpoint/smb/a",
            http_status=404,
        )

    monkeypatch.setattr(registry, "resolve_secret_fields", _boom)
    with pytest.raises(registry.CapsuleActionError) as exc:
        registry.execute_action(
            "test_smb_ntlm",
            {"host": "srv", "username": "u", "secret_ref": "sm://storage-endpoint/smb/a"},
            job_id=3,
        )
    assert exc.value.error_code == "CAPSULE_SECRET_RESOLUTION_FAILED"
    assert exc.value.retryable is False


def test_timeout_error_is_retryable(monkeypatch) -> None:
    def _runner(_payload):
        return False, "operation timeout", {"host": "srv"}

    spec = registry.ALLOWED_ACTIONS["test_smb_ntlm"]
    monkeypatch.setitem(
        registry.ALLOWED_ACTIONS,
        "test_smb_ntlm",
        registry.ActionSpec(
            action=spec.action,
            schema=spec.schema,
            runner=_runner,
            secret_fields=spec.secret_fields,
            target_field=spec.target_field,
        ),
    )
    with pytest.raises(registry.CapsuleActionError) as exc:
        registry.execute_action(
            "test_smb_ntlm",
            {"host": "srv", "username": "u", "password": "p"},
            job_id=4,
        )
    assert exc.value.error_code == "CAPSULE_TIMEOUT"
    assert exc.value.retryable is True


def test_action_failure_preserves_structured_details(monkeypatch) -> None:
    def _runner(_payload):
        return False, "SMB authentication failed", {
            "failure_code": "CAPSULE_AUTH_FAILED",
            "checks": [{"name": "smb_auth", "status": "failed"}],
        }

    spec = registry.ALLOWED_ACTIONS["test_smb_ntlm"]
    monkeypatch.setitem(
        registry.ALLOWED_ACTIONS,
        "test_smb_ntlm",
        registry.ActionSpec(
            action=spec.action,
            schema=spec.schema,
            runner=_runner,
            secret_fields=spec.secret_fields,
            target_field=spec.target_field,
        ),
    )
    with pytest.raises(registry.CapsuleActionError) as exc:
        registry.execute_action(
            "test_smb_ntlm",
            {"host": "srv", "username": "u", "password": "p"},
            job_id=7,
        )
    assert exc.value.error_code == "CAPSULE_AUTH_FAILED"
    assert exc.value.retryable is False
    assert exc.value.details == {
        "failure_code": "CAPSULE_AUTH_FAILED",
        "checks": [{"name": "smb_auth", "status": "failed"}],
    }


def test_smb_root_access_action_is_registered(monkeypatch) -> None:
    def _runner(payload):
        return True, "SMB storage root reachable", {
            "storage_root_id": payload.get("storage_root_id"),
            "checks": [{"name": "root_read", "status": "success"}],
        }

    spec = registry.ALLOWED_ACTIONS["test_smb_root_access"]
    monkeypatch.setitem(
        registry.ALLOWED_ACTIONS,
        "test_smb_root_access",
        registry.ActionSpec(
            action=spec.action,
            schema=spec.schema,
            runner=_runner,
            secret_fields=spec.secret_fields,
            target_field=spec.target_field,
        ),
    )

    result = registry.execute_action(
        "test_smb_root_access",
        {
            "host": "srv",
            "share": "data",
            "path": "finance",
            "username": "u",
            "password": "p",
            "storage_root_id": 42,
        },
        job_id=8,
    )

    assert result["success"] is True
    assert result["details"]["storage_root_id"] == 42


def test_parse_smbclient_du_bytes_extracts_total() -> None:
    from app.actions.smb import _parse_smbclient_du_bytes

    assert _parse_smbclient_du_bytes("Total number of bytes: 123456") == 123456
    assert _parse_smbclient_du_bytes("some text\n123,456 bytes\n") == 123456
    assert _parse_smbclient_du_bytes("no size here") is None


def test_ensure_ad_group_member_requires_principal_identity() -> None:
    with pytest.raises(registry.CapsuleActionError) as exc:
        registry.execute_action(
            "ensure_ad_group_member",
            {
                "host": "dc01.corp.local",
                "bind_dn": "CN=svc,DC=corp,DC=local",
                "password": "secret",
                "base_dn": "DC=corp,DC=local",
                "group_ref": "CN=GRP_X,OU=Groups,DC=corp,DC=local",
            },
            job_id=5,
        )
    assert exc.value.error_code == "CAPSULE_INVALID_PAYLOAD"
    assert exc.value.retryable is False


def test_discover_group_users_recursive_requires_root_group_dn() -> None:
    with pytest.raises(registry.CapsuleActionError) as exc:
        registry.execute_action(
            "discover_group_users_recursive",
            {
                "host": "dc01.corp.local",
                "bind_dn": "CN=svc,DC=corp,DC=local",
                "password": "secret",
                "base_dn": "DC=corp,DC=local",
            },
            job_id=6,
        )
    assert exc.value.error_code == "CAPSULE_INVALID_PAYLOAD"
    assert exc.value.retryable is False
