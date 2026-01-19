from __future__ import annotations
from typing import Iterable, List, Set

# Central RBAC map (permissive default: unknown roles => no perms)
#
# BornToShare (current scope): only 3 platform roles exist.
# - admin: platform administration
# - user: standard portal user
# - audit: read-only + audit views
ROLE_PERMISSIONS = {
    "admin": [
        # Admin UI / configuration
        "identity:read",
        "identity:write",
        "storage_endpoint:read",
        "storage_endpoint:write",
        "storage_root:read",
        "storage_root:write",
        "site:read",
        "site:write",
        "zone:read",
        "zone:write",
        "access_profile:read",
        "access_profile:write",
        "access_request:read",
        "access_request:write",
        "access_request:approve",
        "audit:read",
    ],
    "user": [
        "storage_root:read",
        "access_request:read",
        "access_request:write",
    ],
    "audit": [
        "audit:read",
        "storage_endpoint:read",
        "storage_root:read",
        "access_request:read",
        "identity:read",
    ],
}

def compute_permissions(roles: Iterable[str] | None) -> List[str]:
    perms: Set[str] = set()
    for r in roles or []:
        perms.update(ROLE_PERMISSIONS.get(r, []))
    return sorted(perms)
