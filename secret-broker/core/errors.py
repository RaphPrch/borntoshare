from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class SecretBrokerError(Exception):
    code: str = "SECRET_PROVIDER_FAILURE"
    message: str = "Secret provider failure"
    http_status: int = 500
    ref: Optional[str] = None
    provider: Optional[str] = None

    def __post_init__(self) -> None:
        super().__init__(self.message)


class SecretInvalidRefError(SecretBrokerError):
    def __init__(self, message: str = "Secret ref is invalid", *, ref: Optional[str] = None) -> None:
        super().__init__(
            code="SECRET_INVALID_REF",
            message=message,
            http_status=400,
            ref=ref,
        )


class SecretNotFoundError(SecretBrokerError):
    def __init__(self, message: str = "Secret not found", *, ref: Optional[str] = None, provider: Optional[str] = None) -> None:
        super().__init__(
            code="SECRET_NOT_FOUND",
            message=message,
            http_status=404,
            ref=ref,
            provider=provider,
        )


class SecretDecryptFailedError(SecretBrokerError):
    def __init__(self, message: str = "Secret cannot be decrypted", *, ref: Optional[str] = None, provider: Optional[str] = None) -> None:
        super().__init__(
            code="SECRET_DECRYPT_FAILED",
            message=message,
            http_status=409,
            ref=ref,
            provider=provider,
        )


class SecretPersistenceFailureError(SecretBrokerError):
    def __init__(
        self,
        message: str = "Secret persistence failure",
        *,
        ref: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> None:
        super().__init__(
            code="SECRET_PERSISTENCE_FAILURE",
            message=message,
            http_status=500,
            ref=ref,
            provider=provider,
        )


class SecretProviderFailureError(SecretBrokerError):
    def __init__(self, message: str = "Secret provider failure", *, ref: Optional[str] = None, provider: Optional[str] = None) -> None:
        super().__init__(
            code="SECRET_PROVIDER_FAILURE",
            message=message,
            http_status=500,
            ref=ref,
            provider=provider,
        )


class SecretStoreRejectedError(SecretBrokerError):
    def __init__(self, message: str = "Secret store rejected", *, ref: Optional[str] = None) -> None:
        super().__init__(
            code="SECRET_STORE_REJECTED",
            message=message,
            http_status=403,
            ref=ref,
        )
