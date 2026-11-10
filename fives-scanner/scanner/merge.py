"""A folder is walked in pieces (« chunks »): one per first-level sub-folder, plus the files right in it (key "").
Each chunk keeps its own figures (scan_chunks); after a scan the folder is the sum of its chunks.
Only the chunks where something changed are walked again (USN): the others keep their figures.

Duplicates: inside each chunk as the server found them; between chunks from the fingerprints of the biggest files
(a file present in two chunks counts once per extra chunk).
"""
from __future__ import annotations

from typing import Any


def _int(value: Any) -> int:
    return int(value or 0)


def chunk_of(path: str, local: str) -> str | None:
    """« C:\\Shares\\Finance\\2025\\T1 » under « C:\\Shares\\Finance » → « 2025 »; the folder itself → ""; elsewhere → None."""
    base = local.rstrip("\\").lower()
    value = path.rstrip("\\")
    if value.lower() == base:
        return ""
    if not value.lower().startswith(base + "\\"):
        return None
    return value[len(base) + 1:].split("\\", 1)[0]


def merge(chunks: dict[str, dict[str, Any]], local_path: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"bytes": 0, "files": 0, "folders": 0, "truncated": False, "denied_folders": 0, "method": "server", "local_path": local_path}
    types: dict[str, int] = {}
    cold = {"1y": {"bytes": 0, "files": 0}, "3y": {"bytes": 0, "files": 0}}
    cold_top: list[dict] = []
    junk = {"bytes": 0, "files": 0, "examples": []}
    last: str | None = None
    top: list[dict] = []
    groups = files_in_groups = wasted = hashed = 0
    dup_top: list[dict] = []
    truncated_dups = False
    holders: dict[tuple[str, int], set[str]] = {}
    prints: list[dict] = []
    for key, stats in chunks.items():
        out["bytes"] += _int(stats.get("bytes"))
        out["files"] += _int(stats.get("files"))
        out["folders"] += _int(stats.get("folders")) + (1 if key else 0)
        out["denied_folders"] += _int(stats.get("denied_folders"))
        out["truncated"] = out["truncated"] or bool(stats.get("truncated"))
        if key:
            top.append({"name": key, "bytes": _int(stats.get("bytes")), "files": _int(stats.get("files"))})
        for item in stats.get("types") or []:
            types[item["ext"]] = types.get(item["ext"], 0) + _int(item.get("files"))
        for span in ("1y", "3y"):
            for field in ("bytes", "files"):
                cold[span][field] += _int(((stats.get("cold") or {}).get(span) or {}).get(field))
        cold_top.extend(stats.get("cold_top") or [])
        part = stats.get("junk") or {}
        junk["bytes"] += _int(part.get("bytes"))
        junk["files"] += _int(part.get("files"))
        junk["examples"].extend(part.get("examples") or [])
        if stats.get("last_modified") and (last is None or str(stats["last_modified"]) > last):
            last = str(stats["last_modified"])
        dups = stats.get("duplicates") or {}
        groups += _int(dups.get("groups"))
        files_in_groups += _int(dups.get("files"))
        wasted += _int(dups.get("wasted_bytes"))
        hashed += _int(dups.get("hashed"))
        truncated_dups = truncated_dups or bool(dups.get("truncated"))
        dup_top.extend(dups.get("top") or [])
        for item in stats.get("fingerprints") or []:
            holders.setdefault((str(item.get("fingerprint")), _int(item.get("size"))), set()).add(key)
            prints.append(item)
    # The same file in several chunks: once per extra chunk (copies inside one chunk are already counted by the server)
    for (fingerprint, size), keys in holders.items():
        if len(keys) > 1:
            groups += 1
            files_in_groups += len(keys)
            wasted += size * (len(keys) - 1)
            paths = sorted(item["path"] for item in prints if item.get("fingerprint") == fingerprint and _int(item.get("size")) == size)[:5]
            dup_top.append({"size": size, "files": len(keys), "wasted": size * (len(keys) - 1), "fingerprint": fingerprint, "paths": paths})
    out["top"] = sorted(top, key=lambda item: -item["bytes"])[:8]
    out["types"] = [{"ext": ext, "files": count} for ext, count in sorted(types.items(), key=lambda kv: -kv[1])[:8]]
    out["cold"] = cold
    out["cold_top"] = sorted(cold_top, key=lambda item: -_int(item.get("bytes")))[:5]
    junk["examples"] = junk["examples"][:5]
    out["junk"] = junk
    out["last_modified"] = last
    out["duplicates"] = {"groups": groups, "files": files_in_groups, "wasted_bytes": wasted, "truncated": truncated_dups, "hashed": hashed,
                         "top": sorted(dup_top, key=lambda item: -_int(item.get("wasted")))[:10]}
    # For the duplicates between folders (inventory of the module): the 500 biggest files of the folder
    unique = {(item.get("fingerprint"), item.get("path")): item for item in prints}
    out["fingerprints"] = sorted(unique.values(), key=lambda item: -_int(item.get("size")))[:500]
    return out
