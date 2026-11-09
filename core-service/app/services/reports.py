"""Reports of the governed folders, ready to read on screen or to print (PDF from the browser).

Every report has the same shape, so one page shows them all:
  {key, title, description, generated_at, scope, kpis: [{label, value, type, hint, tone}],
   sections: [{title, description, columns: [{key, label, type}], rows: [...], empty}]}
Column types: text, folder (with its id), bytes, percent, int, date, status. Figures stay raw: the page formats them.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session


# The 5S and data hygiene reports (cold data, duplicates, clutter, growth) belong to the 5S module (fives-service)
KINDS = {
    "storage": ("Stockage et quotas", "Volume des dossiers, par serveur, les plus gros et leurs quotas."),
    "security": ("Sécurité des données", "Mots de passe et clés trouvés, corrections demandées, gardiens et héritage."),
    "governance": ("Gouvernance des accès", "Classement, quotas, demandes en attente et dossiers à revalider."),
}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _col(key: str, label: str, type_: str = "text") -> dict[str, str]:
    return {"key": key, "label": label, "type": type_}


def _kpi(label: str, value: Any, type_: str = "int", hint: str | None = None, tone: str | None = None) -> dict[str, Any]:
    return {"label": label, "value": value, "type": type_, "hint": hint, "tone": tone}


def _folder(row: dict) -> dict[str, Any]:
    return {"id": int(row.get("storage_root_id") or 0), "name": row.get("storage_root_name") or row.get("root_path"),
            "path": row.get("dfs_path") or row.get("root_path")}


def _size(row: dict) -> int:
    return int(row.get("content_size_bytes") or 0)


def _pct(part: float, total: float) -> float | None:
    return round(100 * part / total, 1) if total else None


def _top(rows: list[dict], key: Callable[[dict], float], limit: int = 10) -> list[dict]:
    return sorted([row for row in rows if key(row) > 0], key=key, reverse=True)[:limit]


def storage(db: Session, rows: list[dict]) -> dict[str, Any]:
    measured = [row for row in rows if row.get("content_size_bytes") is not None]
    total = sum(_size(row) for row in measured)
    with_quota = [row for row in rows if row.get("quota_limit_bytes") is not None]
    watch = [row for row in with_quota if row.get("quota_used_percent") is not None
             and float(row["quota_used_percent"]) >= float(row.get("quota_warn_percent") or 85)]
    servers: dict[str, dict[str, Any]] = {}
    for row in measured:
        entry = servers.setdefault(str(row.get("storage_endpoint_name") or "—"), {"server": str(row.get("storage_endpoint_name") or "—"),
                                                                                  "folders": 0, "bytes": 0, "files": 0, "quotas": 0})
        entry["folders"] += 1
        entry["bytes"] += _size(row)
        entry["files"] += int(row.get("content_files") or 0)
        entry["quotas"] += 1 if row.get("quota_limit_bytes") is not None else 0
    quota_rows = [{"folder": _folder(row), "used": row.get("quota_used_bytes"), "limit": row.get("quota_limit_bytes"), "percent": row.get("quota_used_percent"),
                   "status": "plein" if (row.get("quota_used_percent") or 0) >= 100 else "à surveiller" if row in watch else "ok"} for row in with_quota]
    return {
        "kpis": [
            _kpi("Volume mesuré", total, "bytes", f"{len(measured)} dossier(s) mesuré(s) sur {len(rows)}"),
            _kpi("Fichiers", sum(int(row.get("content_files") or 0) for row in measured), "int"),
            _kpi("Dossiers avec quota", len(with_quota), "int", f"{len(watch)} au-delà du seuil d'alerte", "warn" if watch else None),
        ],
        "sections": [
            {"title": "Par serveur", "columns": [_col("server", "Serveur"), _col("folders", "Dossiers", "int"), _col("bytes", "Volume", "bytes"),
                                                  _col("files", "Fichiers", "int"), _col("quotas", "Avec quota", "int")],
             "rows": sorted(servers.values(), key=lambda entry: -entry["bytes"])},
            {"title": "Les plus gros dossiers", "columns": [_col("folder", "Dossier", "folder"), _col("bytes", "Volume", "bytes"),
                                                            _col("files", "Fichiers", "int"), _col("quota", "Quota", "percent")],
             "rows": [{"folder": _folder(row), "bytes": _size(row), "files": row.get("content_files"), "quota": row.get("quota_used_percent")}
                      for row in _top(measured, _size)]},
            {"title": "Quotas", "columns": [_col("folder", "Dossier", "folder"), _col("used", "Utilisé", "bytes"), _col("limit", "Quota", "bytes"),
                                            _col("percent", "Rempli", "percent"), _col("status", "État", "status")],
             "rows": sorted(quota_rows, key=lambda entry: -(entry["percent"] or 0)), "empty": "Aucun dossier n'a de quota."},
        ],
    }


def security(db: Session, rows: list[dict]) -> dict[str, Any]:
    ids = [int(row.get("storage_root_id") or 0) for row in rows]
    by_id = {int(row.get("storage_root_id") or 0): row for row in rows}
    scanned = [row for row in rows if row.get("sensitive_files") is not None]
    with_pw = [row for row in rows if int(row.get("password_files") or 0)]
    with_keys = [row for row in rows if int(row.get("key_files") or 0)]
    corrections = []
    if ids:
        corrections = [dict(row) for row in db.execute(
            text("SELECT storage_root_id, status, files_at_request, requested_by, requested_at, due_at, closed_at FROM sensitivity_remediations "
                 "WHERE storage_root_id IN :ids AND requested_at >= :since ORDER BY requested_at DESC").bindparams(bindparam("ids", expanding=True)),
            {"ids": ids, "since": _now() - timedelta(days=90)},
        ).mappings().all()]
    labels = {"open": "en cours", "overdue": "en retard", "done": "corrigée", "cancelled": "annulée"}
    few_guardians = [row for row in rows if int(row.get("guardians_count") or 0) < 2]
    broken = [row for row in rows if row.get("inheritance_broken") is True]
    return {
        "kpis": [
            _kpi("Dossiers analysés", len(scanned), "int", f"sur {len(rows)}", "warn" if len(scanned) < len(rows) else None),
            _kpi("Avec mots de passe", len(with_pw), "int", None, "bad" if with_pw else "ok"),
            _kpi("Avec clés ou jetons", len(with_keys), "int", None, "bad" if with_keys else "ok"),
            _kpi("Corrections en retard", sum(1 for c in corrections if c["status"] == "overdue"), "int",
                 f"{sum(1 for c in corrections if c['status'] == 'open')} en cours", "bad" if any(c["status"] == "overdue" for c in corrections) else None),
        ],
        "sections": [
            {"title": "Mots de passe et clés trouvés", "columns": [_col("folder", "Dossier", "folder"), _col("passwords", "Mots de passe", "int"),
                                                                   _col("keys", "Clés / jetons", "int"), _col("correction", "Correction", "status")],
             "rows": [{"folder": _folder(row), "passwords": row.get("password_files"), "keys": row.get("key_files"),
                       "correction": labels.get(str(row.get("remediation_status")), "non demandée")}
                      for row in sorted({id(r): r for r in [*with_pw, *with_keys]}.values(),
                                        key=lambda r: -(int(r.get("password_files") or 0) + int(r.get("key_files") or 0)))],
             "empty": "Aucun mot de passe ni aucune clé trouvés."},
            {"title": "Corrections des 90 derniers jours", "columns": [_col("folder", "Dossier", "folder"), _col("status", "État", "status"),
                                                                       _col("files", "Fichiers", "int"), _col("requested_at", "Demandée", "date"),
                                                                       _col("due_at", "Échéance", "date"), _col("closed_at", "Close", "date")],
             "rows": [{"folder": _folder(by_id.get(int(c["storage_root_id"]), {"storage_root_id": c["storage_root_id"]})), "status": labels.get(c["status"], c["status"]),
                       "files": c["files_at_request"], "requested_at": _iso(c["requested_at"]), "due_at": _iso(c["due_at"]), "closed_at": _iso(c["closed_at"])}
                      for c in corrections], "empty": "Aucune correction demandée."},
            {"title": "Gardiens insuffisants", "description": "Moins de deux gardiens : une absence bloque la validation des demandes.",
             "columns": [_col("folder", "Dossier", "folder"), _col("guardians", "Gardiens", "int")],
             "rows": [{"folder": _folder(row), "guardians": int(row.get("guardians_count") or 0)} for row in few_guardians], "empty": "Tous les dossiers ont au moins deux gardiens."},
            {"title": "Héritage rompu", "columns": [_col("folder", "Dossier", "folder")], "rows": [{"folder": _folder(row)} for row in broken],
             "empty": "Aucun dossier à l'héritage rompu."},
        ],
    }


def governance(db: Session, rows: list[dict]) -> dict[str, Any]:
    tagged = [row for row in rows if row.get("tags")]
    with_quota = [row for row in rows if row.get("quota_limit_bytes") is not None]
    waiting = [row for row in rows if int(row.get("pending_validation_count") or 0) or int(row.get("quota_pending_requests") or 0)]
    revalidate = [row for row in rows if row.get("needs_revalidation") is True]
    return {
        "kpis": [
            _kpi("Dossiers gouvernés", len(rows)),
            _kpi("Classés (tag)", _pct(len(tagged), len(rows)), "percent", f"{len(tagged)} dossier(s)"),
            _kpi("Avec quota", _pct(len(with_quota), len(rows)), "percent", f"{len(with_quota)} dossier(s)"),
            _kpi("Demandes en attente", sum(int(row.get("pending_validation_count") or 0) + int(row.get("quota_pending_requests") or 0) for row in rows),
                 "int", f"dans {len(waiting)} dossier(s)", "warn" if waiting else None),
        ],
        "sections": [
            {"title": "Demandes en attente", "columns": [_col("folder", "Dossier", "folder"), _col("access", "Accès", "int"), _col("quota", "Espace", "int"),
                                                         _col("guardians", "Gardiens", "int")],
             "rows": [{"folder": _folder(row), "access": int(row.get("pending_validation_count") or 0), "quota": int(row.get("quota_pending_requests") or 0),
                       "guardians": int(row.get("guardians_count") or 0)} for row in waiting], "empty": "Aucune demande en attente."},
            {"title": "À revalider", "columns": [_col("folder", "Dossier", "folder")], "rows": [{"folder": _folder(row)} for row in revalidate],
             "empty": "Aucun dossier à revalider."},
            {"title": "Sans tag", "columns": [_col("folder", "Dossier", "folder"), _col("server", "Serveur")],
             "rows": [{"folder": _folder(row), "server": row.get("storage_endpoint_name")} for row in rows if not row.get("tags")],
             "empty": "Tous les dossiers sont classés."},
        ],
    }


def _iso(value: Any) -> str | None:
    return value.isoformat() + "Z" if isinstance(value, datetime) else value


BUILDERS = {"storage": storage, "security": security, "governance": governance}


def build(db: Session, kind: str, rows: list[dict], scope: str) -> dict[str, Any]:
    title, description = KINDS[kind]
    return {"key": kind, "title": title, "description": description, "generated_at": _now().isoformat() + "Z", "scope": scope,
            **BUILDERS[kind](db, rows)}
