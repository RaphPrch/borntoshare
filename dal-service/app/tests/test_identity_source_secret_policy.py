from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.identity_sources import IdentitySourceCreate, IdentitySourceUpdate


def _create_payload(**overrides):
    payload = {
        "type": "ad",
        "name": "ad-src",
        "host": "ad.local",
        "bind_password_ref": "sm://kv/ad-src",
    }
    payload.update(overrides)
    return payload


def test_identity_source_create_rejects_plaintext_bind_password() -> None:
    with pytest.raises(ValidationError) as exc:
        IdentitySourceCreate(**_create_payload(bind_password="secret-plain"))

    assert "Plaintext secrets are not allowed" in str(exc.value)


def test_identity_source_update_rejects_plaintext_bind_password() -> None:
    with pytest.raises(ValidationError) as exc:
        IdentitySourceUpdate(bind_password="secret-plain")

    assert "Plaintext secrets are not allowed" in str(exc.value)


def test_identity_source_create_rejects_non_secret_ref_prefix() -> None:
    with pytest.raises(ValidationError) as exc:
        IdentitySourceCreate(**_create_payload(bind_password_ref="vault://bad/ref"))

    assert "bind_password_ref must start with sm://" in str(exc.value)

