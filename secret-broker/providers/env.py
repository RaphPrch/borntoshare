from __future__ import annotations
import os

from core.errors import SecretNotFoundError
from providers.base import SecretProvider

class EnvProvider(SecretProvider):
    prefix = "env://"

    def can_resolve(self, secret_ref: str) -> bool:
        return secret_ref.startswith(self.prefix)

    def resolve(self, secret_ref: str) -> str:
        key = secret_ref[len(self.prefix):]
        val = os.getenv(key)
        if val is None:
            raise SecretNotFoundError(message=f"Missing env var: {key}", ref=secret_ref, provider="env")
        return val
