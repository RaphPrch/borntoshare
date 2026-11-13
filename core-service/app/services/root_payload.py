"""The one way to change what is known of a folder's content (storage_roots.discovered_permissions_json).

The field holds several things written by different jobs: the rights (ACL test, share discovery), the last measure
(content_stats, the kept previous measures, interim figures), the inheritance flags. A writer that rebuilt the whole
dict lost what others had written (the share discovery erased the measures of 21 folders, 2026-11-13). Every writer
merges its own keys here; test_root_payload_single_writer.py refuses any other assignment.
"""
from __future__ import annotations

from typing import Any


def current(root: Any) -> dict[str, Any]:
    value = getattr(root, "discovered_permissions_json", None)
    return dict(value) if isinstance(value, dict) else {}


def merge_root_payload(root: Any, changes: dict[str, Any]) -> dict[str, Any]:
    """Merges these keys into the folder's payload (a new dict: the JSON column is seen as changed). Returns it."""
    merged = {**current(root), **changes}
    root.discovered_permissions_json = merged
    return merged
