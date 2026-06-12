from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.errors import SecretDecryptFailedError, SecretInvalidRefError, SecretNotFoundError
from providers.sm import SecretManagerProvider


def test_resolve_invalid_ref_raises_invalid_ref(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("B2S_SECRETS_DIR", str(tmp_path))
    provider = SecretManagerProvider()

    with pytest.raises(SecretInvalidRefError):
        provider.resolve("sm://")


def test_resolve_missing_file_raises_not_found(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("B2S_SECRETS_DIR", str(tmp_path))
    provider = SecretManagerProvider()

    with pytest.raises(SecretNotFoundError):
        provider.resolve("sm://storage-endpoint/smb/endpoint-a")


def test_resolve_path_traversal_raises_invalid_ref(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("B2S_SECRETS_DIR", str(tmp_path))
    provider = SecretManagerProvider()

    with pytest.raises(SecretInvalidRefError):
        provider.resolve("sm://../etc/passwd")


def test_resolve_corrupted_payload_raises_decrypt_failed(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("B2S_SECRETS_DIR", str(tmp_path))
    provider = SecretManagerProvider()

    target = tmp_path / "storage-endpoint" / "smb"
    target.mkdir(parents=True, exist_ok=True)
    (target / "endpoint-a.enc").write_text("not-json", encoding="utf-8")

    with pytest.raises(SecretDecryptFailedError):
        provider.resolve("sm://storage-endpoint/smb/endpoint-a")


def test_resolve_bad_ciphertext_raises_decrypt_failed(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("B2S_SECRETS_DIR", str(tmp_path))
    monkeypatch.setenv("B2S_SECRET_MASTER_KEY", "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=")
    provider = SecretManagerProvider()

    payload = {
        "iv": base64.b64encode(b"0123456789ab").decode("utf-8"),
        "ciphertext": base64.b64encode(b"bad-ciphertext").decode("utf-8"),
    }

    target = tmp_path / "storage-endpoint" / "smb"
    target.mkdir(parents=True, exist_ok=True)
    (target / "endpoint-a.enc").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SecretDecryptFailedError):
        provider.resolve("sm://storage-endpoint/smb/endpoint-a")
