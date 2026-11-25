"""The one way to change what is known of a folder's content (storage_roots.discovered_permissions_json).

The field holds several things written by different jobs: the rights (ACL test, share discovery), the last measure
(content_stats, the kept previous measures, interim figures), the inheritance flags. A writer that rebuilt the whole
dict lost what others had written (the share discovery erased the measures of 21 folders, 2026-11-13). Every writer
merges its own keys here; test_root_payload_single_writer.py refuses any other assignment.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import object_session


def current(root: Any) -> dict[str, Any]:
    value = getattr(root, "discovered_permissions_json", None)
    return dict(value) if isinstance(value, dict) else {}


def merge_root_payload(root: Any, changes: dict[str, Any]) -> dict[str, Any]:
    """Merges these keys into the folder's payload (a new dict: the JSON column is seen as changed). Returns it."""
    merged = {**current(root), **changes}
    root.discovered_permissions_json = merged
    if "permissions" in changes:
        _index_acl(root, changes.get("permissions"))
    return merged


def acl_index_rows(root_id: int, permissions: Any) -> list[dict[str, Any]]:
    """The entries of storage_root_acl_entries for this ACL (schema/166_access_explorer.sql): principal_key is the
    account name without its domain, lower case, as short_name() and the SQL backfill."""
    rows = []
    for ace in permissions if isinstance(permissions, list) else []:
        principal = str((ace or {}).get("principal") or "").strip() if isinstance(ace, dict) else ""
        if not principal:
            continue
        key = principal.replace("/", "\\").split("\\")[-1].strip().lower()[:190]
        rows.append({"root": int(root_id), "principal": principal[:512], "key": key, "raw": str(ace.get("raw") or "")[:255] or None})
    return rows


def _index_acl(root: Any, permissions: Any) -> None:
    """The ACE index of the Access Explorer follows the ACL, in the same transaction. A folder not stored yet (no id)
    gets its index at its first ACL read."""
    root_id = getattr(root, "id", None)
    try:
        session = object_session(root)
    except Exception:
        session = None
    if session is None or not root_id:
        return
    session.execute(text("DELETE FROM storage_root_acl_entries WHERE storage_root_id = :root"), {"root": int(root_id)})
    rows = acl_index_rows(int(root_id), permissions)
    if rows:
        session.execute(
            text("INSERT INTO storage_root_acl_entries (storage_root_id, principal, principal_key, raw) VALUES (:root, :principal, :key, :raw)"),
            rows,
        )
