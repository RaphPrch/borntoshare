"""Internal service-to-service authentication helpers."""

from __future__ import annotations

import os
import time
from typing import Dict, Iterable

from app.core.config import get_settings
from app.core.logging import get_request_id_context


def build_internal_headers(request_id: str | None = None) -> Dict[str, str]:
    settings = get_settings()
    tok = (getattr(settings, "INTERNAL_TOKEN", "") or "").strip()
    service_name = (getattr(settings, "INTERNAL_SERVICE_NAME", "") or "").strip() or "auth"
    service_scope = (getattr(settings, "INTERNAL_SERVICE_SCOPE", "") or "").strip() or "jobs:read"
    resolved_request_id = (request_id or get_request_id_context() or "").strip()

    headers: Dict[str, str] = {"X-Internal-Token": tok} if tok else {}
    # The token of auth-service (H4): core-service knows the caller by it, not by X-Service-Name
    own = (os.getenv("B2S_SERVICE_TOKEN") or "").strip()
    if own:
        headers["X-Service-Token"] = own
    if service_name:
        headers["X-Service-Name"] = service_name
    if service_scope:
        headers["X-Service-Scope"] = service_scope
    if resolved_request_id:
        headers["X-Request-ID"] = resolved_request_id
    return headers


def actor_assertion(identity_id: int | None, roles: Iterable[str], display_name: str | None) -> str:
    """The person auth-service acts for, signed for core-service (X-B2S-Actor): same format as the BFF's (valid 60 s,
    audience « core », key of the principal cookie). core-service believes no identity header without it (H4)."""
    from app.core.principal_snapshot import sign_principal_payload

    return sign_principal_payload({
        "id": identity_id,
        "roles": sorted({str(r).strip().lower() for r in roles if str(r).strip()}),
        "name": display_name,
        "aud": "core",
        "exp": int(time.time()) + 60,
    })
