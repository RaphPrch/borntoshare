from __future__ import annotations

import base64
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from core.crypto import get_master_key
from core.errors import (
    SecretDecryptFailedError,
    SecretInvalidRefError,
    SecretNotFoundError,
)
from providers.base import SecretProvider
from providers.path_utils import sm_ref_to_file_path


class SecretManagerProvider(SecretProvider):
    prefix = "sm://"

    def can_resolve(self, secret_ref: str) -> bool:
        return secret_ref.startswith(self.prefix)

    def resolve(self, secret_ref: str) -> str:
        base_dir = (
            os.getenv("B2S_SECRETS_DIR")
            or os.getenv("B2S_SECRET_STORE_DIR")
            or "/data/secrets"
        ).strip()
        try:
            target = sm_ref_to_file_path(Path(base_dir), secret_ref)
        except SecretInvalidRefError:
            raise
        except Exception as exc:
            raise SecretInvalidRefError(ref=secret_ref) from exc

        if not target.exists():
            raise SecretNotFoundError(ref=secret_ref, provider="filesystem")

        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
            iv = base64.b64decode(payload["iv"])
            ciphertext = base64.b64decode(payload["ciphertext"])
        except Exception as exc:
            raise SecretDecryptFailedError(
                message="Secret exists but encrypted payload is corrupted",
                ref=secret_ref,
                provider="filesystem",
            ) from exc

        key = get_master_key()
        aes = AESGCM(key)
        try:
            plaintext = aes.decrypt(iv, ciphertext, None)
        except Exception as exc:
            raise SecretDecryptFailedError(
                message="Secret exists but cannot be decrypted",
                ref=secret_ref,
                provider="filesystem",
            ) from exc
        return plaintext.decode("utf-8")
