from __future__ import annotations

"""Internal service-to-service authentication helpers."""

from typing import Dict

from app.core.config import get_settings
from app.core.logging import get_request_id_context


def build_internal_headers(request_id: str | None = None) -> Dict[str, str]:
    settings = get_settings()
    tok = (getattr(settings, "INTERNAL_TOKEN", "") or "").strip()
    service_tok = (getattr(settings, "SERVICE_TOKEN", "") or "").strip()
    service_name = (getattr(settings, "INTERNAL_SERVICE_NAME", "") or "").strip() or "auth"
    service_scope = (getattr(settings, "INTERNAL_SERVICE_SCOPE", "") or "").strip() or "jobs:read"
    resolved_request_id = (request_id or get_request_id_context() or "").strip()

    headers: Dict[str, str] = {"X-Internal-Token": tok} if tok else {}
    if service_tok:
        headers["X-Service-Token"] = service_tok
    if service_name:
        headers["X-Service-Name"] = service_name
    if service_scope:
        headers["X-Service-Scope"] = service_scope
    if resolved_request_id:
        headers["X-Request-ID"] = resolved_request_id
    return headers
