from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, Sequence

from app.services.secret_broker_client import SecretResolveError, resolve_secret_refs


@dataclass
class CapsuleSecretResolutionError(RuntimeError):
    error_code: str
    message: str
    secret_ref: str
    http_status: Optional[int] = None

    def __post_init__(self) -> None:
        super().__init__(self.message)


def _collect_secret_refs(payload: Dict[str, Any], fields: Sequence[str]) -> list[str]:
    refs: list[str] = []
    for field in fields:
        value = payload.get(field)
        if isinstance(value, str) and value.strip().startswith("sm://"):
            refs.append(value.strip())

    # De-dup while preserving order
    out: list[str] = []
    seen = set()
    for ref in refs:
        if ref in seen:
            continue
        seen.add(ref)
        out.append(ref)
    return out


def resolve_secret_fields(payload: Dict[str, Any], secret_fields: Sequence[str]) -> Dict[str, Any]:
    out = dict(payload or {})
    refs = _collect_secret_refs(out, secret_fields)
    if not refs:
        return out

    try:
        resolved = resolve_secret_refs(refs)
    except SecretResolveError as exc:
        raise CapsuleSecretResolutionError(
            error_code=exc.code,
            message=exc.message,
            secret_ref=exc.ref,
            http_status=exc.http_status,
        ) from exc

    for field in secret_fields:
        ref = out.get(field)
        if isinstance(ref, str) and ref.strip().startswith("sm://"):
            secret_value = resolved.get(ref.strip())
            if secret_value is None:
                raise CapsuleSecretResolutionError(
                    error_code="CAPSULE_SECRET_RESOLUTION_FAILED",
                    message=f"Missing resolved value for {ref}",
                    secret_ref=ref,
                    http_status=500,
                )
            # Convention: map secret_ref -> password unless explicitly handled upstream.
            if not out.get("password"):
                out["password"] = secret_value

    return out

