from __future__ import annotations

from fastapi import HTTPException, Request, status


def get_internal_headers(request: Request) -> dict[str, str]:
    internal_token = str(request.headers.get("X-Internal-Token") or "").strip()
    if not internal_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error_code": "MISSING_INTERNAL_TOKEN",
                "message": "Missing internal token",
            },
        )

    headers = {
        "accept": "application/json",
        "X-Internal-Token": internal_token,
    }

    request_id = str(request.headers.get("X-Request-ID") or "").strip()
    if request_id:
        headers["X-Request-ID"] = request_id

    service_name = str(request.headers.get("X-Service-Name") or "").strip()
    if service_name:
        headers["X-Service-Name"] = service_name

    service_scope = str(request.headers.get("X-Service-Scope") or "").strip()
    if service_scope:
        headers["X-Service-Scope"] = service_scope

    service_token = str(request.headers.get("X-Service-Token") or "").strip()
    if service_token:
        headers["X-Service-Token"] = service_token

    return headers
