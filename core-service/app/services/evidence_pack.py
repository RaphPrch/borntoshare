"""Audit evidence pack: one ZIP of CSV files for a scope (everything, a zone, a folder) and a period.

What happened (the chained audit log, with its hashes), the access requests and their decisions, the decisions of
the access reviews and, for a folder, who reaches it today. A MANIFEST gives the scope, the period, who exported it,
and the SHA-256 of every file, so that a copy can be checked later. Read only.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.logging_db import LoggingSessionLocal

MAX_EVENTS = 200_000
MAX_DAYS = 400


def _csv(header: list[str], rows: Iterable[Iterable[Any]]) -> tuple[bytes, int]:
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";", lineterminator="\r\n")
    writer.writerow(header)
    count = 0
    for row in rows:
        # A cell starting with = + - @ is not run as a formula by a spreadsheet
        writer.writerow(["'" + v if isinstance(v, str) and v[:1] in "=+-@" else ("" if v is None else v) for v in row])
        count += 1
    return ("﻿" + out.getvalue()).encode("utf-8"), count


def _iso(value: Any) -> str:
    return value.isoformat() + "Z" if isinstance(value, datetime) else ("" if value is None else str(value))


def _folder_ids(db: Session, *, root_id: int | None, zone_id: int | None) -> list[int] | None:
    """The folders of the scope (None: every folder)."""
    if root_id:
        return [int(root_id)]
    if zone_id:
        rows = db.execute(text("""SELECT sr.id FROM storage_roots sr JOIN storage_endpoints se ON se.id = sr.storage_endpoint_id
                                  WHERE se.zone_id = :zone"""), {"zone": int(zone_id)}).all()
        return [int(row[0]) for row in rows]
    return None


def _events(since: datetime, until: datetime, *, root_id: int | None, zone_id: int | None) -> tuple[bytes, int]:
    where = ["event_time >= :since", "event_time < :until", "action NOT LIKE 'http.%' AND action NOT LIKE 'api.%' AND action NOT LIKE 'ui.%'"]
    params: dict[str, Any] = {"since": since, "until": until, "limit": MAX_EVENTS}
    if root_id:
        where.append("root_id = :root")
        params["root"] = int(root_id)
    elif zone_id:
        where.append("zone_id = :zone")
        params["zone"] = int(zone_id)
    with LoggingSessionLocal() as db:
        rows = db.execute(text(f"""
            SELECT event_time, action, result, severity, actor_type, actor_id, entity_type, entity_id, zone_id, root_id,
                   correlation_id, source_service, metadata_json, hash_prev, hash_current
            FROM audit_event WHERE {' AND '.join(where)} ORDER BY event_time LIMIT :limit"""), params).mappings().all()

    def lines():
        for row in rows:
            meta = row["metadata_json"]
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except ValueError:
                    meta = {}
            meta = meta if isinstance(meta, dict) else {}
            yield [_iso(row["event_time"]), row["action"], row["result"], row["severity"], row["actor_type"], row["actor_id"],
                   meta.get("actor_display") or "", row["entity_type"], row["entity_id"], row["zone_id"], row["root_id"],
                   row["correlation_id"], row["source_service"],
                   json.dumps(meta.get("context_json") or {}, ensure_ascii=False, sort_keys=True, default=str),
                   row["hash_prev"], row["hash_current"]]

    return _csv(["time_utc", "action", "result", "severity", "actor_type", "actor_id", "actor", "target_type", "target_id",
                 "zone_id", "storage_root_id", "correlation_id", "service", "context", "hash_prev", "hash_current"], lines())


def _requests(db: Session, since: datetime, until: datetime, folders: list[int] | None) -> tuple[bytes, int]:
    scope = "" if folders is None else ("AND ari.target_id IN :folders" if folders else "AND 1 = 0")
    statement = text(f"""
        SELECT ar.id, ar.code, ar.status, ar.created_at, ar.decided_at, ar.revoked_at, ar.decision_comment,
               ar.requested_principal_json, req.username AS requester, sr.id AS root_id, sr.name AS root_name, sr.root_path,
               ari.permission, ari.expires_at
        FROM access_requests ar
        JOIN access_request_items ari ON ari.access_request_id = ar.id AND ari.target_type = 'storage_root'
        LEFT JOIN storage_roots sr ON sr.id = ari.target_id
        LEFT JOIN identities req ON req.id = ar.requester_identity_id
        WHERE ((ar.created_at >= :since AND ar.created_at < :until) OR (ar.decided_at >= :since AND ar.decided_at < :until)
               OR (ar.revoked_at >= :since AND ar.revoked_at < :until)) {scope}
        ORDER BY ar.created_at""")
    if folders:
        from sqlalchemy import bindparam

        statement = statement.bindparams(bindparam("folders", expanding=True))
    rows = db.execute(statement, {"since": since, "until": until, **({"folders": folders} if folders else {})}).mappings().all()

    def lines():
        for row in rows:
            principal = row["requested_principal_json"]
            if isinstance(principal, str):
                try:
                    principal = json.loads(principal)
                except ValueError:
                    principal = {}
            principal = principal if isinstance(principal, dict) else {}
            yield [row["code"] or f"REQ-{row['id']}", row["status"], row["requester"], principal.get("username") or principal.get("display_name") or "",
                   row["root_id"], row["root_name"], row["root_path"], row["permission"], _iso(row["created_at"]), _iso(row["decided_at"]),
                   _iso(row["expires_at"]), _iso(row["revoked_at"]), row["decision_comment"]]

    return _csv(["request", "status", "requested_by", "for", "storage_root_id", "folder", "path", "level", "created_utc",
                 "decided_utc", "expires_utc", "revoked_utc", "comment"], lines())


def _reviews(db: Session, since: datetime, until: datetime, folders: list[int] | None) -> tuple[bytes, int]:
    scope = "" if folders is None else ("AND i.storage_root_id IN :folders" if folders else "AND 1 = 0")
    statement = text(f"""
        SELECT r.name AS review, i.storage_root_id, sr.name AS root_name, i.username, i.display_name, i.level, i.decision,
               i.note, i.decided_by, i.decided_at, i.outcome
        FROM access_review_items i JOIN access_reviews r ON r.id = i.review_id
        LEFT JOIN storage_roots sr ON sr.id = i.storage_root_id
        WHERE i.decided_at >= :since AND i.decided_at < :until {scope}
        ORDER BY i.decided_at""")
    if folders:
        from sqlalchemy import bindparam

        statement = statement.bindparams(bindparam("folders", expanding=True))
    rows = db.execute(statement, {"since": since, "until": until, **({"folders": folders} if folders else {})}).mappings().all()
    return _csv(["review", "storage_root_id", "folder", "login", "name", "level", "decision", "note", "decided_by", "decided_utc", "outcome"],
                ([row["review"], row["storage_root_id"], row["root_name"], row["username"], row["display_name"], row["level"], row["decision"],
                  row["note"], row["decided_by"], _iso(row["decided_at"]), row["outcome"]] for row in rows))


def _access_today(db: Session, root_id: int) -> tuple[bytes, int]:
    from app.services.storage_root_permissions import StorageRootPermissions

    result = StorageRootPermissions(db).build(int(root_id)) or {}

    def via(person: dict[str, Any]) -> str:
        return ", ".join(str(v.get("code") or v.get("group") or v.get("kind")) for v in person.get("via") or [])

    return _csv(["login", "name", "level", "through", "expires_utc"],
                ([p.get("username"), p.get("name"), p.get("level"), via(p), p.get("expires_at")] for p in result.get("people") or []))


def build(db: Session, *, since: date, until: date, root_id: int | None = None, zone_id: int | None = None,
          by: str | None = None) -> tuple[bytes, str]:
    """The ZIP and its file name. `until` is included (the whole day)."""
    start = datetime.combine(since, datetime.min.time())
    end = datetime.combine(until + timedelta(days=1), datetime.min.time())
    folders = _folder_ids(db, root_id=root_id, zone_id=zone_id)
    files: list[tuple[str, bytes, int, str]] = []
    data, count = _events(start, end, root_id=root_id, zone_id=zone_id)
    files.append(("audit_events.csv", data, count, "Journal d'audit chaîné (hash_prev, hash_current)"))
    data, count = _requests(db, start, end, folders)
    files.append(("access_requests.csv", data, count, "Demandes d'accès faites, décidées ou retirées sur la période"))
    data, count = _reviews(db, start, end, folders)
    files.append(("access_reviews.csv", data, count, "Décisions des revues d'accès sur la période"))
    if root_id:
        data, count = _access_today(db, int(root_id))
        files.append(("access_today.csv", data, count, "Qui accède au dossier à la date de l'export"))
    scope = f"dossier {root_id}" if root_id else (f"zone {zone_id}" if zone_id else "toute la plateforme")
    now = datetime.now(timezone.utc)
    manifest = [
        "BornToShare · pack de preuves d'audit",
        f"Exporté le : {now.isoformat(timespec='seconds')}",
        f"Par : {by or '—'}",
        f"Périmètre : {scope}",
        f"Période : du {since.isoformat()} au {until.isoformat()} inclus (UTC)",
        "",
        "Fichiers (lignes · SHA-256 · contenu) :",
        *[f"- {name} · {count} · {hashlib.sha256(data).hexdigest()} · {what}" for name, data, count, what in files],
        "",
        "Le journal d'audit est chaîné : chaque événement porte le hash du précédent (hash_prev) et le sien (hash_current).",
        f"Au plus {MAX_EVENTS} événements ; au-delà, réduisez la période.",
    ]
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data, _count, _what in files:
            archive.writestr(name, data)
        archive.writestr("MANIFEST.txt", ("\n".join(manifest) + "\n").encode("utf-8"))
    label = f"root{root_id}" if root_id else (f"zone{zone_id}" if zone_id else "all")
    return out.getvalue(), f"b2s-evidence-{label}-{since.isoformat()}-{until.isoformat()}.zip"
