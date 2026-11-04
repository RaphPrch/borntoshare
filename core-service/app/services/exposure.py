"""Exposure map: how widely each governed folder is open, from the last ACL read of its folder.

A folder is « open » when an Everyone-like principal (Everyone, Users, Domain users…) reaches it whatever the requests
say, « outside » when an account that BornToShare does not manage reaches it, « governed » when only its AD groups
and the expected system accounts do. Accepted gaps (Permissions tab) do not count.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.storage_root_permissions import (
    _json,
    is_broad_principal,
    is_expected_system_principal,
    rights_from_raw,
    short_name,
)

LEVELS = ("open_write", "open_read", "outside", "governed", "unknown")


def classify(aces: list[dict[str, Any]], *, scanned: bool, governed: set[str], accepted: set[str], service_account: str | None) -> dict[str, Any]:
    broad: dict[str, dict[str, Any]] = {}
    outside: set[str] = set()
    for ace in aces:
        principal = str(ace.get("principal") or "").strip()
        raw = str(ace.get("raw") or "")
        rights = rights_from_raw(raw)
        if not principal or rights == "deny" or short_name(principal) in governed or principal.lower() in accepted:
            continue
        if is_broad_principal(principal):
            write = rights in ("modify", "full")
            seen = broad.get(principal.lower())
            parts = raw.split("/")
            inherited = len(parts) >= 2 and "I" in parts[1].split("|")
            if seen is None or (write and not seen["write"]):
                broad[principal.lower()] = {"principal": principal, "rights": rights, "write": write, "inherited": inherited}
        elif not is_expected_system_principal(principal, service_account):
            outside.add(principal.lower())
    if not scanned:
        level = "unknown"
    elif any(entry["write"] for entry in broad.values()):
        level = "open_write"
    elif broad:
        level = "open_read"
    elif outside:
        level = "outside"
    else:
        level = "governed"
    return {"level": level, "broad": list(broad.values()), "outside_count": len(outside)}


def _share_of(path: str) -> str:
    parts = [part for part in str(path or "").replace("/", "\\").split("\\") if part]
    return "\\\\" + "\\".join(parts[:2]) if len(parts) >= 2 else str(path or "")


def build_exposure(db: Session, allowed_root_ids: set[int] | None) -> dict[str, Any]:
    rows = db.execute(
        text(
            """
            SELECT sr.id, sr.name, sr.root_path, sr.discovered_permissions_json,
                   se.id AS endpoint_id, se.name AS endpoint_name, se.bind_dn AS endpoint_account,
                   z.id AS zone_id, z.name AS zone_name
            FROM storage_roots sr
            JOIN storage_endpoints se ON se.id = sr.storage_endpoint_id
            JOIN zones z ON z.id = se.zone_id
            WHERE sr.deleted_at IS NULL
            ORDER BY z.name, se.name, sr.root_path
            """
        )
    ).mappings().all()
    governed: dict[int, set[str]] = {}
    for row in db.execute(
        text("SELECT storage_root_id, group_name FROM storage_root_access_profiles WHERE group_name IS NOT NULL")
    ).mappings():
        governed.setdefault(int(row["storage_root_id"]), set()).add(short_name(row["group_name"]))
    accepted: dict[int, set[str]] = {}
    try:
        for row in db.execute(text("SELECT storage_root_id, principal FROM storage_root_acl_exceptions")).mappings():
            accepted.setdefault(int(row["storage_root_id"]), set()).add(str(row["principal"] or "").lower())
    except Exception:  # table not created yet (pack 136)
        db.rollback()

    summary = {level: 0 for level in LEVELS}
    zones: dict[int, dict[str, Any]] = {}
    for row in rows:
        root_id = int(row["id"])
        if allowed_root_ids is not None and root_id not in allowed_root_ids:
            continue
        scan = _json(row.get("discovered_permissions_json"))
        aces = [dict(a) for a in (scan.get("permissions") or []) if isinstance(a, dict)]
        state = classify(
            aces,
            scanned=bool(scan.get("discovered_at") or aces),
            governed=governed.get(root_id, set()),
            accepted=accepted.get(root_id, set()),
            service_account=row.get("endpoint_account"),
        )
        summary[state["level"]] += 1
        zone = zones.setdefault(int(row["zone_id"]), {"zone_id": int(row["zone_id"]), "zone": row["zone_name"], "servers": {}})
        server = zone["servers"].setdefault(
            int(row["endpoint_id"]), {"endpoint_id": int(row["endpoint_id"]), "server": row["endpoint_name"], "shares": {}}
        )
        share = _share_of(str(row["root_path"] or ""))
        server["shares"].setdefault(share, []).append(
            {"id": root_id, "name": row["name"], "path": row["root_path"], "scanned_at": scan.get("discovered_at"), **state}
        )
    return {
        "summary": {**summary, "total": sum(summary.values())},
        "zones": [
            {
                "zone_id": zone["zone_id"],
                "zone": zone["zone"],
                "servers": [
                    {
                        "endpoint_id": server["endpoint_id"],
                        "server": server["server"],
                        "shares": [{"share": share, "folders": folders} for share, folders in server["shares"].items()],
                    }
                    for server in zone["servers"].values()
                ],
            }
            for zone in zones.values()
        ],
    }
