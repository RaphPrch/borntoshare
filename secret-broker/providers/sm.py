from __future__ import annotations

from core import crypto, store
from core.errors import SecretDecryptFailedError, SecretNotFoundError
from providers.base import SecretProvider
from providers.path_utils import build_sm_ref


class SecretManagerProvider(SecretProvider):
    prefix = "sm://"

    def can_resolve(self, secret_ref: str) -> bool:
        return secret_ref.startswith(self.prefix)

    def resolve(self, secret_ref: str) -> str:
        ref = build_sm_ref(secret_ref)
        row = store.get(ref)
        if row is None:
            raise SecretNotFoundError(ref=secret_ref, provider="database")
        try:
            return crypto.decrypt(ref, row["iv"], row["ciphertext"])
        except Exception as exc:
            raise SecretDecryptFailedError(
                message="Secret exists but cannot be decrypted",
                ref=secret_ref,
                provider="database",
            ) from exc
