from __future__ import annotations
import logging
import httpx

from app.core.config import get_settings
from app.core.internal_token import build_internal_headers
from app.core.logging import get_logger, log_event
from app.services.providers.base import AuthProvider, AuthUnavailable, InvalidCredentials
from app.schemas.auth import UserInfo

settings = get_settings()
logger = get_logger(__name__)


class DalLocalProvider(AuthProvider):
    name = "local"

    @staticmethod
    def _extract_detail(response: httpx.Response) -> str:
        try:
            payload = response.json() if response.content else {}
            if isinstance(payload, dict):
                return str(payload.get("detail") or payload)
            return str(payload)
        except ValueError:
            return (response.text or "")[:256]

    @staticmethod
    def _raise_auth_error_for_status(status_code: int, *, detail: str, operation: str) -> None:
        if status_code in {401, 403}:
            raise InvalidCredentials("Invalid credentials")
        if status_code >= 500:
            raise AuthUnavailable(f"DAL {operation} unavailable")
        raise AuthUnavailable(f"DAL {operation} bad response: {status_code} {detail}")

    async def authenticate(self, username: str, password: str) -> UserInfo:
        url = settings.DAL_URL.rstrip("/") + settings.DAL_VALIDATE_CREDENTIALS_PATH
        payload = {"username": username, "password": password}
        timeout = getattr(settings, "DAL_TIMEOUT_SECONDS", 5)

        log_event(
            logger,
            logging.DEBUG,
            "AUTH_PROVIDER_LOCAL_CALL",
            provider="local",
            actor=username,
            target=url,
            outcome="attempt",
        )

        # 🔐 Service-to-service auth headers (X-Internal-Token + X-Service-Token when configured)
        headers = build_internal_headers()

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            log_event(
                logger,
                logging.ERROR,
                "AUTH_PROVIDER_UNAVAILABLE",
                provider="local",
                actor=username,
                target=url,
                outcome="timeout",
                error_code="INTERNAL_ERROR",
                message=str(exc),
            )
            raise AuthUnavailable("DAL local provider timeout") from exc
        except httpx.RequestError as exc:
            log_event(
                logger,
                logging.ERROR,
                "AUTH_PROVIDER_UNAVAILABLE",
                provider="local",
                actor=username,
                target=url,
                outcome="network_error",
                error_code="INTERNAL_ERROR",
                message=str(exc),
            )
            raise AuthUnavailable("DAL local provider unavailable") from exc

        if r.status_code != 200:
            detail = self._extract_detail(r)
            log_event(
                logger,
                logging.WARNING if r.status_code < 500 else logging.ERROR,
                "AUTH_LOGIN_FAILED" if r.status_code in {401, 403} else "AUTH_PROVIDER_UNAVAILABLE",
                provider="local",
                actor=username,
                target=url,
                outcome="invalid_credentials" if r.status_code in {401, 403} else "dal_error",
                status_code=r.status_code,
                error_code="UNAUTHENTICATED" if r.status_code in {401, 403} else "INTERNAL_ERROR",
                message=detail,
            )
            self._raise_auth_error_for_status(r.status_code, detail=detail, operation="authenticate")

        try:
            data = r.json() if r.content else {}
        except ValueError as exc:
            log_event(
                logger,
                logging.ERROR,
                "AUTH_PROVIDER_UNAVAILABLE",
                provider="local",
                actor=username,
                target=url,
                outcome="invalid_json",
                error_code="INTERNAL_ERROR",
            )
            raise AuthUnavailable("DAL authenticate bad response") from exc

        if not isinstance(data, dict):
            raise AuthUnavailable("DAL authenticate bad response")

        identity_id = str(data.get("identity_id") or "").strip()
        if not identity_id:
            raise AuthUnavailable("DAL authenticate invalid contract: identity_id is required")

        return UserInfo(
            identity_id=identity_id,
            username=data.get("username") or username,
            display_name=data.get("display_name"),
            email=data.get("email"),
            auth_source="local",
            external_id=identity_id,
            is_admin=False,
        )

    async def change_password(
        self,
        username: str,
        current_password: str | None,
        new_password: str,
    ) -> None:
        url = settings.DAL_URL.rstrip("/") + settings.DAL_CHANGE_PASSWORD_PATH
        payload = {
            "username": username,
            "current_password": current_password or None,
            "new_password": new_password,
        }
        timeout = getattr(settings, "DAL_TIMEOUT_SECONDS", 5)

        log_event(
            logger,
            logging.INFO,
            "AUTH_PROVIDER_LOCAL_CALL",
            provider="local",
            actor=username,
            target=url,
            outcome="change_password_attempt",
        )

        headers = build_internal_headers()

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                r = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            log_event(
                logger,
                logging.ERROR,
                "AUTH_PROVIDER_UNAVAILABLE",
                provider="local",
                actor=username,
                target=url,
                outcome="timeout",
                error_code="INTERNAL_ERROR",
                message=str(exc),
            )
            raise AuthUnavailable("DAL local provider timeout") from exc
        except httpx.RequestError as exc:
            log_event(
                logger,
                logging.ERROR,
                "AUTH_PROVIDER_UNAVAILABLE",
                provider="local",
                actor=username,
                target=url,
                outcome="network_error",
                error_code="INTERNAL_ERROR",
                message=str(exc),
            )
            raise AuthUnavailable("DAL local provider unavailable") from exc

        if r.status_code != 200:
            detail = self._extract_detail(r)
            log_event(
                logger,
                logging.WARNING if r.status_code < 500 else logging.ERROR,
                "AUTH_CHANGE_PASSWORD_FAILED" if r.status_code in {401, 403} else "AUTH_PROVIDER_UNAVAILABLE",
                provider="local",
                actor=username,
                target=url,
                outcome="invalid_credentials" if r.status_code in {401, 403} else "dal_error",
                status_code=r.status_code,
                error_code="BAD_REQUEST" if r.status_code in {401, 403} else "INTERNAL_ERROR",
                message=detail,
            )
            self._raise_auth_error_for_status(r.status_code, detail=detail, operation="change_password")
