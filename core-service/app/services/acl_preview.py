"""What an approval will change in the NTFS permissions of a folder, before anything is done (dry run).

Read only: compares the ACL of the folder as last read on its file server (storage_roots.discovered_permissions_json,
refreshed by the probes and the Permissions tab) with the entry the approval adds — the access group of the level,
« this folder, subfolders and files » — and names the risks. Nothing is written, no job is started: the approval
itself stays the explicit confirmation.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.storage_root_permissions import (
    inheritance_state,
    is_broad_principal,
    is_expected_system_principal,
    rights_from_raw,
    short_name,
)

ACL_STALE_DAYS = 7
_RANK = {"deny": 0, "special": 1, "read": 2, "modify": 3, "full": 4}


def _load(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value) if value else {}
    except (TypeError, ValueError):
        return {}


def _age_days(value: Any) -> int | None:
    try:
        read_at = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if read_at.tzinfo is None:
        read_at = read_at.replace(tzinfo=timezone.utc)
    return max(0, (datetime.now(timezone.utc) - read_at).days)


def _entries(permissions: list[Any], *, account: str | None, managed: set[str]) -> list[dict[str, Any]]:
    """One line per account, its strongest right; a DENY entry stays apart (it overrides an ALLOW)."""
    out: dict[tuple[str, bool], dict[str, Any]] = {}
    for item in permissions:
        if not isinstance(item, dict) or not item.get("principal"):
            continue
        principal = str(item["principal"])
        raw = str(item.get("raw") or "")
        rights = rights_from_raw(raw)
        deny = rights == "deny"
        flags = raw.upper().split("/")
        inherited = len(flags) > 2 and "I" in flags[1].split("|")
        name = short_name(principal)
        kind = ("managed" if name in managed else "system" if is_expected_system_principal(principal, account)
                else "broad" if is_broad_principal(principal) else "other")
        key = (name, deny)
        row = out.get(key)
        if row is None or _RANK.get(rights, 0) > _RANK.get(row["rights"], 0):
            out[key] = {"principal": principal, "rights": rights, "kind": kind, "inherited": inherited}
    return sorted(out.values(), key=lambda r: (["managed", "other", "broad", "system"].index(r["kind"]), r["principal"].lower()))


def preview(db: Session, storage_root_id: int, group_name: str | None, access_level: str) -> dict[str, Any]:
    target = "modify" if str(access_level).upper() == "WRITE" else "read"
    row = db.execute(text("""
        SELECT sr.root_path, sr.discovered_permissions_json, se.bind_dn AS endpoint_account
        FROM storage_roots sr LEFT JOIN storage_endpoints se ON se.id = sr.storage_endpoint_id
        WHERE sr.id = :id"""), {"id": int(storage_root_id)}).mappings().first()
    managed = {short_name(r[0]) for r in db.execute(
        text("SELECT group_name FROM storage_root_access_profiles WHERE storage_root_id = :id"), {"id": int(storage_root_id)})}
    discovered = _load((row or {}).get("discovered_permissions_json"))
    permissions = discovered.get("permissions") if isinstance(discovered.get("permissions"), list) else None
    group = short_name(group_name)
    risks: list[dict[str, Any]] = []
    out: dict[str, Any] = {"target": {"principal": group_name, "rights": target, "scope": "this_folder_subfolders_files"},
                           "read_at": discovered.get("discovered_at") if permissions is not None else None, "current": [],
                           "change": "unknown", "change_from": None, "risks": risks}

    # The level asked gives write on the whole share when the folder is its root (\\server\share)
    parts = [p for p in str((row or {}).get("root_path") or "").replace("/", "\\").split("\\") if p]
    if target == "modify" and len(parts) == 2:
        risks.append({"code": "SHARE_ROOT_WRITE", "values": {"path": (row or {}).get("root_path")}})

    if permissions is None:
        risks.append({"code": "ACL_NOT_READ", "values": {}})
        return out
    age = _age_days(discovered.get("discovered_at"))
    if age is not None and age > ACL_STALE_DAYS:
        risks.append({"code": "ACL_READ_OLD", "values": {"days": age}})

    entries = _entries(permissions, account=(row or {}).get("endpoint_account"), managed=managed | ({group} if group else set()))
    out["current"] = entries
    mine = next((e for e in entries if short_name(e["principal"]) == group and e["rights"] != "deny"), None)
    if mine is None:
        out["change"] = "add"
    elif _RANK.get(mine["rights"], 0) >= _RANK[target]:
        out["change"] = "present"
    else:
        out["change"], out["change_from"] = "level_change", mine["rights"]

    broad = [e for e in entries if e["kind"] == "broad" and e["rights"] != "deny"]
    if broad:
        risks.append({"code": "BROAD_ACCESS", "values": {"names": [e["principal"] for e in broad[:5]], "count": len(broad)}})
    manual = [e for e in entries if e["kind"] == "other" and e["rights"] != "deny"]
    if manual:
        risks.append({"code": "MANUAL_ENTRIES", "values": {"names": [e["principal"] for e in manual[:5]], "count": len(manual)}})
    deny = [e for e in entries if e["rights"] == "deny"]
    if deny:
        risks.append({"code": "DENY_ENTRIES", "values": {"names": [e["principal"] for e in deny[:5]], "count": len(deny)}})
    if inheritance_state(discovered.get("control"), permissions)["broken"]:
        risks.append({"code": "INHERITANCE_BROKEN", "values": {}})
    return out
