from __future__ import annotations

from typing import Literal


def normalize_requested_permission(permission: str | None) -> Literal["READ", "WRITE"] | None:
    raw = str(permission or "").strip().lower()
    if raw in {
        "read",
        "read_ntfs",
        "read-only",
        "read_only",
        "audit",
    }:
        return "READ"
    if raw in {
        "write",
        "write_ntfs",
        "modify",
        "read_write",
        "read-write",
        "contribution",
        "change",
        "owner",
        "admin",
        "full",
        "fullcontrol",
        "full_control",
        "rw",
        "rwx",
    }:
        return "WRITE"
    return None

