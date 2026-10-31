from __future__ import annotations

import base64

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from core import crypto
from core.errors import SecretDecryptFailedError, SecretInvalidRefError, SecretNotFoundError
from providers.sm import SecretManagerProvider

REF = "sm://storage-endpoint/smb/endpoint-a"


@pytest.fixture(autouse=True)
def _key(monkeypatch) -> None:
    monkeypatch.setenv("B2S_SECRET_MASTER_KEY", base64.b64encode(b"0123456789abcdef0123456789abcdef").decode())


def _row(ref: str, value: str) -> dict:
    iv, ciphertext = crypto.encrypt(ref, value)
    return {"iv": iv, "ciphertext": ciphertext, "key_id": "k"}


def test_resolve_decrypts_the_row(rows) -> None:
    rows[REF] = _row(REF, "secret")
    assert SecretManagerProvider().resolve(REF) == "secret"
    assert "secret" not in str(rows)


def test_resolve_invalid_ref_raises_invalid_ref(rows) -> None:
    with pytest.raises(SecretInvalidRefError):
        SecretManagerProvider().resolve("sm://")


def test_resolve_path_traversal_raises_invalid_ref(rows) -> None:
    with pytest.raises(SecretInvalidRefError):
        SecretManagerProvider().resolve("sm://../etc/passwd")


def test_resolve_missing_row_raises_not_found(rows) -> None:
    with pytest.raises(SecretNotFoundError):
        SecretManagerProvider().resolve(REF)


def test_resolve_corrupted_row_raises_decrypt_failed(rows) -> None:
    rows[REF] = {"iv": "not base64!", "ciphertext": "x", "key_id": "k"}
    with pytest.raises(SecretDecryptFailedError):
        SecretManagerProvider().resolve(REF)


def test_a_value_copied_to_another_reference_cannot_be_decrypted(rows) -> None:
    rows[REF] = _row("sm://other/secret", "secret")
    with pytest.raises(SecretDecryptFailedError):
        SecretManagerProvider().resolve(REF)


def test_another_key_cannot_decrypt(rows, monkeypatch) -> None:
    iv = b"0123456789ab"
    other = AESGCM(b"f" * 32).encrypt(iv, b"secret", REF.encode())
    rows[REF] = {"iv": base64.b64encode(iv).decode(), "ciphertext": base64.b64encode(other).decode(), "key_id": "k"}
    with pytest.raises(SecretDecryptFailedError):
        SecretManagerProvider().resolve(REF)
