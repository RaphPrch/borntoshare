from __future__ import annotations

def resolve_ntfs_rights(access_level: str, permission_hash: str | None):
    _ = permission_hash
    if access_level == "READ":
        return ["READ", "EXECUTE"]
    if access_level == "WRITE":
        return ["MODIFY"]
    raise ValueError("Unsupported access level: only READ/WRITE are allowed")
