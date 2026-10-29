"""Guards of the file servers and storage roots: changes that would leave AD groups, ACLs or accesses behind.

- the host of a file server is also written in the UNC path of its storage roots (\\\\host\\share\\folder)
- the AD groups of a root live in the domain of the identity source and in the OU of the zone
- an access (approved request) or a pending request points at its storage root
"""
from __future__ import annotations

import ipaddress
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

# Levels that have an AD group in the directory (created or adopted)
_GROUP_STATUSES = ("SUCCEEDED", "ADOPTING")


def unc_host(path: str | None) -> str | None:
    """Host of a UNC path (\\\\host\\share or //host/share), None otherwise."""
    raw = str(path or "").strip().replace("/", "\\")
    if not raw.startswith("\\\\"):
        return None
    host = raw[2:].split("\\", 1)[0].strip()
    return host or None


def same_host(a: str | None, b: str | None) -> bool:
    """Same server: equal names, or a short name and its FQDN (fs12 / fs12.example.org), or equal IPs."""
    left, right = str(a or "").strip().lower().rstrip("."), str(b or "").strip().lower().rstrip(".")
    if not left or not right:
        return False
    if left == right:
        return True
    try:
        ipaddress.ip_address(left)
        ipaddress.ip_address(right)
        return False  # two different IPs
    except ValueError:
        pass
    return left.split(".", 1)[0] == right.split(".", 1)[0] and ("." not in left or "." not in right)


def rewrite_unc_host(path: str, new_host: str) -> str:
    """\\\\old\\share\\folder -> \\\\new\\share\\folder (anything after the host is kept)."""
    raw = str(path or "").strip()
    if not unc_host(raw):
        return raw
    rest = raw.replace("/", "\\")[2:].split("\\", 1)
    return f"\\\\{new_host}" + (f"\\{rest[1]}" if len(rest) > 1 else "")


def normalize_root_path(value: str | None) -> str:
    """Same normalization as the storage roots (forward slashes, lower case, no trailing slash)."""
    raw = str(value or "").strip().replace("\\", "/")
    while "//" in raw:
        raw = raw.replace("//", "/")
    return raw.rstrip("/").lower()


def endpoint_root_count(db: Session, endpoint_id: int) -> int:
    return int(
        db.execute(text("SELECT COUNT(*) FROM storage_roots WHERE storage_endpoint_id = :id"), {"id": int(endpoint_id)}).scalar()
        or 0
    )


def endpoint_access_group_count(db: Session, endpoint_id: int) -> int:
    """AD access groups already in the directory for the roots of a file server."""
    return int(
        db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM storage_root_access_profiles p
                JOIN storage_roots sr ON sr.id = p.storage_root_id
                WHERE sr.storage_endpoint_id = :id AND UPPER(COALESCE(p.status, '')) IN ('SUCCEEDED', 'ADOPTING')
                """
            ),
            {"id": int(endpoint_id)},
        ).scalar()
        or 0
    )


def root_access_group_count(db: Session, root_id: int) -> int:
    return int(
        db.execute(
            text(
                """
                SELECT COUNT(*) FROM storage_root_access_profiles
                WHERE storage_root_id = :id AND UPPER(COALESCE(status, '')) IN ('SUCCEEDED', 'ADOPTING')
                """
            ),
            {"id": int(root_id)},
        ).scalar()
        or 0
    )


def root_access_counts(db: Session, root_id: int) -> dict[str, int]:
    """Active accesses (approved, not revoked, not expired) and pending requests of a storage root."""
    row = db.execute(
        text(
            """
            SELECT
              COUNT(DISTINCT CASE WHEN LOWER(ar.status) IN ('approved', 'executed') AND ar.revoked_at IS NULL
                                       AND (ari.expires_at IS NULL OR ari.expires_at > UTC_TIMESTAMP())
                                  THEN ar.id END) AS active,
              COUNT(DISTINCT CASE WHEN LOWER(ar.status) = 'pending' THEN ar.id END) AS pending
            FROM access_request_items ari
            JOIN access_requests ar ON ar.id = ari.access_request_id
            WHERE LOWER(COALESCE(ari.target_type, '')) = 'storage_root' AND ari.target_id = :id
            """
        ),
        {"id": int(root_id)},
    ).mappings().first()
    return {"active": int((row or {}).get("active") or 0), "pending": int((row or {}).get("pending") or 0)}


def endpoint_access_counts(db: Session, endpoint_id: int) -> dict[str, Any]:
    """Same counts for all the roots of a file server."""
    row = db.execute(
        text(
            """
            SELECT
              COUNT(DISTINCT CASE WHEN LOWER(ar.status) IN ('approved', 'executed') AND ar.revoked_at IS NULL
                                       AND (ari.expires_at IS NULL OR ari.expires_at > UTC_TIMESTAMP())
                                  THEN ar.id END) AS active,
              COUNT(DISTINCT CASE WHEN LOWER(ar.status) = 'pending' THEN ar.id END) AS pending
            FROM access_request_items ari
            JOIN access_requests ar ON ar.id = ari.access_request_id
            JOIN storage_roots sr ON sr.id = ari.target_id
            WHERE LOWER(COALESCE(ari.target_type, '')) = 'storage_root' AND sr.storage_endpoint_id = :id
            """
        ),
        {"id": int(endpoint_id)},
    ).mappings().first()
    return {"active": int((row or {}).get("active") or 0), "pending": int((row or {}).get("pending") or 0)}
