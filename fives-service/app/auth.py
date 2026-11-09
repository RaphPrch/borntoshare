"""Who calls: the BFF forwards the person (x-identity-id, x-roles, x-actor-display) with the shared internal token;
the module trusts the identity only with that token, like core-service."""
from __future__ import annotations

import hmac
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

from app.config import settings


@dataclass(frozen=True)
class Actor:
    identity_id: int | None
    roles: frozenset[str]
    display_name: str | None

    @property
    def is_admin(self) -> bool:
        return "platform_admin" in self.roles or "admin" in self.roles

    def headers(self) -> dict[str, str]:
        out = {"x-roles": ",".join(sorted(self.roles))}
        if self.identity_id is not None:
            out["x-identity-id"] = str(self.identity_id)
        if self.display_name:
            out["x-actor-display"] = self.display_name
        return out


def check_internal_token(request: Request) -> None:
    provided = request.headers.get("x-internal-token", "")
    if not provided or not hmac.compare_digest(provided, settings.INTERNAL_TOKEN):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"error_code": "INTERNAL_TOKEN_REQUIRED", "message": "Internal token required"})


def actor(request: Request) -> Actor:
    check_internal_token(request)
    raw = request.headers.get("x-identity-id")
    roles = frozenset(part.strip().lower() for part in str(request.headers.get("x-roles") or "").split(",") if part.strip())
    return Actor(identity_id=int(raw) if raw and raw.isdigit() else None, roles=roles,
                 display_name=str(request.headers.get("x-actor-display") or "").strip() or None)
