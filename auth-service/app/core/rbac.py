from __future__ import annotations
from typing import Iterable, List, Set

# Central RBAC map (permissive default: unknown roles => no perms)
ROLE_PERMISSIONS = {
    "admin": [
        "dataspace:read","dataspace:write",
        "policy:read","policy:write",
        "pack:read","pack:write",
        "tag:read","tag:write",
        "site:read","site:write",
        "zone:read","zone:write",
        "user:read","user:write",
        "access_request:approve",
        "guardian:take","guardian:release",
    ],
    "readonly": [
        "dataspace:read","policy:read","pack:read","tag:read",
        "site:read","zone:read","user:read"
    ],
    "guardian": [
        "dataspace:read",
        "access_request:approve",
        "guardian:take","guardian:release",
    ],
}

def compute_permissions(roles: Iterable[str] | None) -> List[str]:
    perms: Set[str] = set()
    for r in roles or []:
        perms.update(ROLE_PERMISSIONS.get(r, []))
    return sorted(perms)
