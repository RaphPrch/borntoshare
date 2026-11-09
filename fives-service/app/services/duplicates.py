"""Duplicates between folders (b2s_fives_inventory.fingerprints): the same fingerprint in two folders is the same file.

Fingerprint = SHA-256 of the size, the first and the last 64 KiB, computed on the file server by the measure; the
biggest files of each folder (at most 500), replaced at each measure.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session


def _parse(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None) if value else None
    except ValueError:
        return None


def replace(db: Session, storage_root_id: int, prints: list[dict]) -> int:
    db.execute(text("DELETE FROM fingerprints WHERE storage_root_id = :id"), {"id": int(storage_root_id)})
    rows = [
        {"id": int(storage_root_id), "fp": str(item.get("fingerprint"))[:64], "size": int(item.get("size") or 0),
         "path": str(item.get("path") or "")[:1024], "at": _parse(item.get("modified"))}
        for item in prints[:500] if item.get("fingerprint") and item.get("path")
    ]
    if rows:
        db.execute(text("INSERT INTO fingerprints (storage_root_id, fingerprint, size_bytes, path, modified_at) VALUES (:id, :fp, :size, :path, :at)"), rows)
    return len(rows)


def shared(db: Session, storage_root_ids: list[int]) -> dict[int, dict[str, Any]]:
    """Per folder (among these): its files also present in other folders of these, their size, which folders."""
    ids = sorted({int(value) for value in storage_root_ids if int(value) > 0})
    if not ids:
        return {}
    rows = db.execute(
        text(
            """
            SELECT f.storage_root_id, f.fingerprint, f.size_bytes, f.path FROM fingerprints f
            JOIN (SELECT fingerprint, size_bytes FROM fingerprints WHERE storage_root_id IN :ids GROUP BY fingerprint, size_bytes
                  HAVING COUNT(DISTINCT storage_root_id) > 1) d ON d.fingerprint = f.fingerprint AND d.size_bytes = f.size_bytes
            WHERE f.storage_root_id IN :ids
            """
        ).bindparams(bindparam("ids", expanding=True)),
        {"ids": ids},
    ).all()
    by_print: dict[tuple[str, int], list[tuple[int, str]]] = {}
    for root_id, fingerprint, size, path in rows:
        by_print.setdefault((str(fingerprint), int(size)), []).append((int(root_id), str(path)))
    out: dict[int, dict[str, Any]] = {}
    for (_fingerprint, size), holders in by_print.items():
        roots = {root_id for root_id, _path in holders}
        for root_id, path in holders:
            entry = out.setdefault(root_id, {"files": 0, "bytes": 0, "with": set(), "examples": []})
            entry["files"] += 1
            entry["bytes"] += size
            entry["with"].update(roots - {root_id})
            if len(entry["examples"]) < 5:
                entry["examples"].append({"path": path, "size": size,
                                          "also_in": sorted(other for other_root, other in holders if other_root != root_id)[:3]})
    for entry in out.values():
        entry["with"] = sorted(entry["with"])
    return out


def total(db: Session, storage_root_ids: list[int]) -> dict[str, int]:
    """Room that removing the extra copies between these folders would free: each shared file counts (copies - 1)."""
    ids = sorted({int(value) for value in storage_root_ids if int(value) > 0})
    if not ids:
        return {"bytes": 0, "files": 0}
    row = db.execute(
        text(
            """
            SELECT COALESCE(SUM(size_bytes * (copies - 1)), 0), COUNT(*) FROM (
              SELECT size_bytes, COUNT(DISTINCT storage_root_id) AS copies FROM fingerprints WHERE storage_root_id IN :ids
              GROUP BY fingerprint, size_bytes HAVING COUNT(DISTINCT storage_root_id) > 1) shared
            """
        ).bindparams(bindparam("ids", expanding=True)),
        {"ids": ids},
    ).first()
    return {"bytes": int(row[0] or 0), "files": int(row[1] or 0)}
