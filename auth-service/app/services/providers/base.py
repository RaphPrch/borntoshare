from __future__ import annotations
from abc import ABC, abstractmethod

from app.schemas.auth import UserInfo


class AuthUnavailable(Exception):
    """Provider is enabled but currently unreachable (network, timeout, etc.)."""


class InvalidCredentials(Exception):
    """Credentials were checked and are invalid."""


class ProviderMisconfigured(Exception):
    """Provider configuration is invalid or incomplete."""


class SecretResolutionError(Exception):
    """Provider secret resolution failed."""

class AuthProvider(ABC):
    name: str

    @abstractmethod
    async def authenticate(self, username: str, password: str) -> UserInfo:
        raise NotImplementedError

    async def change_password(
        self,
        username: str,
        current_password: str | None,
        new_password: str,
    ) -> None:
        raise NotImplementedError("change_password not supported")
