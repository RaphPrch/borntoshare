"""Folders to suggest in a new access request: the ones my team works in, the ones I asked for before, the ones
most asked for. From the requests themselves (always there), and the directory to know my team."""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

# A group larger than this says nothing about a team (« Domain users »…)
TEAM_GROUP_MAX = 60
GRANTED = "LOWER(ar.status) IN ('approved', 'executed') AND ar.revoked_at IS NULL"


def _rows(db: Session, sql: str, params: dict[str, Any]) -> list[tuple[int, int]]:
    try:
        return [(int(root), int(count)) for root, count in db.execute(text(sql), params).all() if root]
    except Exception:
        db.rollback()
        return []


def suggestions(db: Session, identity_id: int | None, limit: int = 8) -> dict[str, list[dict[str, int]]]:
    me = int(identity_id or 0)
    # The folders I already have or am waiting for are not suggested again
    mine = {root for root, _ in _rows(db, f"""
        SELECT DISTINCT ari.target_id, 1 FROM access_request_items ari JOIN access_requests ar ON ar.id = ari.access_request_id
        WHERE ari.target_type = 'storage_root' AND ar.requester_identity_id = :me
          AND ({GRANTED} OR LOWER(ar.status) = 'pending')""", {"me": me})}

    team = _rows(db, f"""
        SELECT ari.target_id, COUNT(DISTINCT ar.requester_identity_id) AS n
        FROM access_request_items ari JOIN access_requests ar ON ar.id = ari.access_request_id
        JOIN identities colleague ON colleague.id = ar.requester_identity_id
        JOIN directory_users cdu ON cdu.identity_source_id = colleague.source_id
             AND (cdu.external_id = colleague.external_id OR LOWER(cdu.username) = LOWER(colleague.username))
        JOIN directory_effective_memberships cm ON cm.directory_user_id = cdu.id
        WHERE ari.target_type = 'storage_root' AND {GRANTED} AND ar.requester_identity_id <> :me
          AND cm.directory_group_id IN (
            SELECT mm.directory_group_id FROM identities i
            JOIN directory_users du ON du.identity_source_id = i.source_id AND (du.external_id = i.external_id OR LOWER(du.username) = LOWER(i.username))
            JOIN directory_effective_memberships mm ON mm.directory_user_id = du.id
            WHERE i.id = :me
              AND mm.directory_group_id IN (SELECT directory_group_id FROM directory_effective_memberships GROUP BY directory_group_id HAVING COUNT(*) <= :max))
        GROUP BY ari.target_id ORDER BY n DESC LIMIT 30""", {"me": me, "max": TEAM_GROUP_MAX})
    recent = _rows(db, """
        SELECT ari.target_id, COUNT(*) FROM access_request_items ari JOIN access_requests ar ON ar.id = ari.access_request_id
        WHERE ari.target_type = 'storage_root' AND ar.requester_identity_id = :me
        GROUP BY ari.target_id ORDER BY MAX(ar.created_at) DESC LIMIT 30""", {"me": me})
    popular = _rows(db, f"""
        SELECT ari.target_id, COUNT(DISTINCT ar.requester_identity_id) AS n
        FROM access_request_items ari JOIN access_requests ar ON ar.id = ari.access_request_id
        WHERE ari.target_type = 'storage_root' AND {GRANTED} AND ar.created_at > UTC_TIMESTAMP() - INTERVAL 180 DAY
        GROUP BY ari.target_id ORDER BY n DESC LIMIT 30""", {})

    def keep(rows: list[tuple[int, int]]) -> list[dict[str, int]]:
        return [{"storage_root_id": root, "count": count} for root, count in rows if root not in mine][:limit]

    return {"team": keep(team), "recent": keep(recent), "popular": keep(popular)}
