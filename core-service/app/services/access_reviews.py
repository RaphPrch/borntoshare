"""Access review campaigns (Access Management › Reviews).

An administrator opens a campaign on every governed folder or some of them: each person who reaches a folder at that
time is listed (the permissions of the folder: requests, AD groups, groups outside BornToShare), and the guardians of
the folder keep or remove each access. Removing an access granted by a request revokes it (its AD group membership
goes: api/governance/access_reviews.py); an access that does not come from BornToShare is « to handle by hand ».
Everything is in the chained audit log, and the closed campaign is the evidence of the review.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.services.authorization import ActorContext, get_guardian_storage_root_ids, is_platform_administrator


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(value: Any) -> str | None:
    return value.isoformat() + "Z" if isinstance(value, datetime) else None


def _refuse(code: str, message: str, http: int = status.HTTP_409_CONFLICT) -> HTTPException:
    return HTTPException(status_code=http, detail={"error_code": code, "message": message})


def _visible_roots(db: Session, actor: ActorContext) -> set[int] | None:
    """None: every folder (administrator); else the folders this person guards."""
    return None if is_platform_administrator(actor) else set(get_guardian_storage_root_ids(db, actor))


def governed_root_ids(db: Session) -> list[int]:
    return [int(row[0]) for row in db.execute(text("SELECT id FROM storage_roots ORDER BY id")).all()]


def guardians_of(db: Session, root_ids: list[int]) -> dict[int, list[dict[str, Any]]]:
    """The guardians of these folders: {root: [{identity_id, email}]}."""
    if not root_ids:
        return {}
    rows = db.execute(text("""
        SELECT srr.root_id, i.id, i.email FROM storage_root_roles srr JOIN identities i ON i.id = srr.identity_id
        WHERE LOWER(COALESCE(srr.role, '')) = 'guardian' AND i.is_active = 1 AND srr.root_id IN :ids""")
                      .bindparams(bindparam("ids", expanding=True)), {"ids": root_ids}).all()
    out: dict[int, list[dict[str, Any]]] = {}
    for root_id, identity_id, email in rows:
        out.setdefault(int(root_id), []).append({"identity_id": int(identity_id), "email": email})
    return out


def open_review(db: Session, actor: ActorContext, *, name: str, root_ids: list[int] | None, due_at: datetime | None) -> dict[str, Any]:
    """Open a campaign: one item per person and folder, from the permissions of each folder now."""
    from app.services.storage_root_permissions import StorageRootPermissions

    if not is_platform_administrator(actor):
        raise _refuse("ACCESS_REVIEW_ADMIN_ONLY", "Only an administrator opens a review", status.HTTP_403_FORBIDDEN)
    targets = sorted(set(int(value) for value in root_ids)) if root_ids else governed_root_ids(db)
    if not targets:
        raise _refuse("ACCESS_REVIEW_NO_FOLDER", "No governed folder to review")
    now = _now()
    review_id = int(db.execute(text("""
        INSERT INTO access_reviews (name, status, scope_root_ids, due_at, created_by_identity_id, created_by, created_at)
        VALUES (:name, 'open', :scope, :due, :by_id, :by, :now)"""), {
        "name": name.strip()[:190], "scope": json.dumps(targets) if root_ids else None, "due": due_at,
        "by_id": actor.identity_id, "by": actor.display_name, "now": now}).lastrowid)
    service = StorageRootPermissions(db)
    items = 0
    for root_id in targets:
        built = service.build(root_id)
        for person in (built or {}).get("people") or []:
            key = str(person.get("key") or person.get("username") or person.get("name") or "").lower()[:190]
            if not key:
                continue
            db.execute(text("""
                INSERT IGNORE INTO access_review_items (review_id, storage_root_id, person_key, username, display_name, level, via_json, revocable_request_ids)
                VALUES (:review, :root, :key, :username, :name, :level, :via, :revocable)"""), {
                "review": review_id, "root": root_id, "key": key, "username": person.get("username"), "name": str(person.get("name") or key)[:255],
                "level": person.get("level"), "via": json.dumps(person.get("via") or [], default=str)[:60000],
                "revocable": ",".join(str(value) for value in person.get("revocable_request_ids") or [])[:500] or None})
            items += 1
    db.commit()
    return {"id": review_id, "items": items, "folders": len(targets), "root_ids": targets}


def list_reviews(db: Session, actor: ActorContext) -> list[dict[str, Any]]:
    """The campaigns with their progress (for a guardian: the part of their folders only)."""
    roots = _visible_roots(db, actor)
    if roots is not None and not roots:
        return []
    where, params = "", {}
    if roots is not None:
        where, params = "WHERE i.storage_root_id IN :roots", {"roots": sorted(roots)}
    sql = f"""
        SELECT r.id, r.name, r.status, r.due_at, r.created_by, r.created_at, r.closed_at, r.closed_by,
               COUNT(i.id) AS total, SUM(i.decision IS NOT NULL) AS decided, SUM(i.decision = 'revoke') AS revoke_count,
               SUM(i.decision = 'keep') AS keep_count, SUM(i.outcome = 'revoked') AS revoked, SUM(i.outcome = 'manual') AS manual,
               SUM(i.outcome = 'failed') AS failed, COUNT(DISTINCT i.storage_root_id) AS folders
        FROM access_reviews r {"JOIN" if roots is not None else "LEFT JOIN"} access_review_items i ON i.review_id = r.id {where}
        GROUP BY r.id ORDER BY r.status = 'open' DESC, r.created_at DESC LIMIT 100"""
    statement = text(sql).bindparams(bindparam("roots", expanding=True)) if roots is not None else text(sql)
    out = []
    for row in db.execute(statement, params).mappings().all():
        out.append({**{k: row[k] for k in ("id", "name", "status", "created_by", "closed_by")},
                    **{k: int(row[k] or 0) for k in ("total", "decided", "revoked", "manual", "failed", "folders")},
                    "revoke": int(row["revoke_count"] or 0),
                    "keep": int(row["keep_count"] or 0), "due_at": _iso(row["due_at"]), "created_at": _iso(row["created_at"]),
                    "closed_at": _iso(row["closed_at"])})
    return out


def _review(db: Session, review_id: int) -> dict[str, Any]:
    row = db.execute(text("SELECT * FROM access_reviews WHERE id = :id"), {"id": int(review_id)}).mappings().first()
    if not row:
        raise _refuse("ACCESS_REVIEW_NOT_FOUND", "Review not found", status.HTTP_404_NOT_FOUND)
    return dict(row)


def items(db: Session, actor: ActorContext, review_id: int) -> dict[str, Any]:
    """The people to review in this campaign (for a guardian: on their folders), with the folder they reach."""
    review = _review(db, review_id)
    roots = _visible_roots(db, actor)
    where, params = "i.review_id = :id", {"id": int(review_id)}
    if roots is not None:
        if not roots:
            raise _refuse("ACCESS_REVIEW_FORBIDDEN", "You guard no folder of this review", status.HTTP_403_FORBIDDEN)
        where += " AND i.storage_root_id IN :roots"
        params["roots"] = sorted(roots)
    statement = text(f"""SELECT i.*, sr.name AS root_name, sr.root_path FROM access_review_items i JOIN storage_roots sr ON sr.id = i.storage_root_id
                         WHERE {where} ORDER BY sr.name, i.display_name""")
    if roots is not None:
        statement = statement.bindparams(bindparam("roots", expanding=True))
    rows = []
    for row in db.execute(statement, params).mappings().all():
        try:
            via = json.loads(row["via_json"] or "[]")
        except ValueError:
            via = []
        rows.append({"id": int(row["id"]), "storage_root_id": int(row["storage_root_id"]), "root_name": row["root_name"], "root_path": row["root_path"],
                     "username": row["username"], "display_name": row["display_name"], "level": row["level"], "via": via,
                     "revocable": bool(row["revocable_request_ids"]), "decision": row["decision"], "note": row["note"],
                     "decided_by": row["decided_by"], "decided_at": _iso(row["decided_at"]), "outcome": row["outcome"],
                     "outcome_detail": row["outcome_detail"]})
    return {"review": {"id": int(review["id"]), "name": review["name"], "status": review["status"], "due_at": _iso(review["due_at"]),
                       "created_at": _iso(review["created_at"]), "created_by": review["created_by"], "closed_at": _iso(review["closed_at"])},
            "items": rows}


def decide(db: Session, actor: ActorContext, review_id: int, item_ids: list[int], decision: str | None, note: str | None) -> int:
    """Keep or remove these accesses (None: back to « to decide »), on the folders this person may review."""
    review = _review(db, review_id)
    if review["status"] != "open":
        raise _refuse("ACCESS_REVIEW_CLOSED", "This review is closed")
    if decision not in ("keep", "revoke", None):
        raise _refuse("ACCESS_REVIEW_DECISION_INVALID", "Keep or revoke", status.HTTP_422_UNPROCESSABLE_ENTITY)
    ids = sorted({int(value) for value in item_ids})
    if not ids:
        return 0
    roots = _visible_roots(db, actor)
    where = "review_id = :review AND id IN :ids AND outcome IS NULL"
    params: dict[str, Any] = {"review": int(review_id), "ids": ids, "decision": decision, "note": (note or None) and note[:500],
                              "by": actor.display_name, "at": _now() if decision else None}
    statement = f"UPDATE access_review_items SET decision = :decision, note = :note, decided_by = :by, decided_at = :at WHERE {where}"
    if roots is not None:
        statement += " AND storage_root_id IN :roots"
        params["roots"] = sorted(roots) or [0]
    bound = text(statement).bindparams(bindparam("ids", expanding=True))
    if roots is not None:
        bound = bound.bindparams(bindparam("roots", expanding=True))
    changed = int(db.execute(bound, params).rowcount or 0)
    db.commit()
    return changed


def pending_removals(db: Session, actor: ActorContext, review_id: int) -> list[dict[str, Any]]:
    """The accesses decided « remove » and not applied yet, on the folders this person may review."""
    data = items(db, actor, review_id)
    rows = db.execute(text("""SELECT id, revocable_request_ids FROM access_review_items
                              WHERE review_id = :id AND decision = 'revoke' AND outcome IS NULL"""), {"id": int(review_id)}).all()
    revocable = {int(row[0]): [int(value) for value in str(row[1] or "").split(",") if value.strip().isdigit()] for row in rows}
    return [{**item, "request_ids": revocable[item["id"]]} for item in data["items"] if item["id"] in revocable]


def record_outcome(db: Session, item_id: int, outcome: str, detail: str | None = None) -> None:
    db.execute(text("UPDATE access_review_items SET outcome = :outcome, outcome_detail = :detail WHERE id = :id"),
               {"id": int(item_id), "outcome": outcome, "detail": (detail or None) and str(detail)[:500]})
    db.commit()


def close_review(db: Session, actor: ActorContext, review_id: int) -> dict[str, Any]:
    if not is_platform_administrator(actor):
        raise _refuse("ACCESS_REVIEW_ADMIN_ONLY", "Only an administrator closes a review", status.HTTP_403_FORBIDDEN)
    review = _review(db, review_id)
    if review["status"] != "open":
        raise _refuse("ACCESS_REVIEW_CLOSED", "This review is already closed")
    db.execute(text("UPDATE access_reviews SET status = 'closed', closed_at = :now, closed_by = :by WHERE id = :id"),
               {"id": int(review_id), "now": _now(), "by": actor.display_name})
    db.commit()
    counts = db.execute(text("""SELECT COUNT(*), SUM(decision IS NULL), SUM(decision = 'keep'), SUM(decision = 'revoke'), SUM(outcome = 'revoked')
                                FROM access_review_items WHERE review_id = :id"""), {"id": int(review_id)}).first()
    return {"id": int(review_id), "total": int(counts[0] or 0), "undecided": int(counts[1] or 0), "kept": int(counts[2] or 0),
            "removed": int(counts[3] or 0), "revoked": int(counts[4] or 0)}


def notify_guardians(db: Session, review_id: int, name: str, root_ids: list[int], due_at: datetime | None) -> int:
    """The bell (and a mail when they are switched on) for every guardian of the folders of the campaign."""
    from app.services import inbox, notifications

    by_root = guardians_of(db, root_ids)
    people = {guardian["identity_id"]: guardian.get("email") for guardians in by_root.values() for guardian in guardians}
    when = f" avant le {due_at:%d/%m/%Y}" if due_at else ""
    title = f"Revue des accès « {name} » : vos dossiers sont à revoir{when}"
    body = "Pour chaque personne qui accède à vos dossiers, gardez ou retirez l'accès."
    link = f"/access-reviews/{int(review_id)}"
    inbox.push(db, list(people), f"access_review:{int(review_id)}", kind="review", severity="warning", title=title, body=body, link=link)
    emails = [email for email in people.values() if email]
    config = notifications.settings(db)
    if emails and config.get("enabled"):
        notifications.queue(f"access_review:{int(review_id)}", emails, f"[BornToShare] {title}", body + notifications._link(config, link))
    return len(people)
