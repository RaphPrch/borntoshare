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

from app.services import content_history, five_s

KINDS = {
    "storage": ("Stockage et quotas", "Volume, croissance, quotas, données froides et fichiers parasites des dossiers."),
    "security": ("Sécurité des données", "Mots de passe et clés trouvés, corrections demandées, gardiens et héritage."),
    "governance": ("Gouvernance des accès", "Classement, quotas, demandes en attente et dossiers à revalider."),
    "five_s": ("5S des partages", "Score 5S des dossiers, par pilier et par zone, et les actions qui l'amélioreraient."),
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
    cold1 = sum(int(row.get("cold_1y_bytes") or 0) for row in measured)
    cold3 = sum(int(row.get("cold_3y_bytes") or 0) for row in measured)
    junk = sum(int(row.get("junk_bytes") or 0) for row in measured)
    with_quota = [row for row in rows if row.get("quota_limit_bytes") is not None]
    watch = [row for row in with_quota if row.get("quota_used_percent") is not None
             and float(row["quota_used_percent"]) >= float(row.get("quota_warn_percent") or 85)]
    servers: dict[str, dict[str, Any]] = {}
    for row in measured:
        entry = servers.setdefault(str(row.get("storage_endpoint_name") or "—"), {"server": str(row.get("storage_endpoint_name") or "—"),
                                                                                  "folders": 0, "bytes": 0, "cold": 0, "quotas": 0})
        entry["folders"] += 1
        entry["bytes"] += _size(row)
        entry["cold"] += int(row.get("cold_1y_bytes") or 0)
        entry["quotas"] += 1 if row.get("quota_limit_bytes") is not None else 0
    quota_rows = []
    for row in with_quota:
        forecast = content_history.forecast(_size(row) or row.get("quota_used_bytes"), row.get("quota_limit_bytes"), row.get("bytes_per_day"))
        quota_rows.append({"folder": _folder(row), "used": row.get("quota_used_bytes"), "limit": row.get("quota_limit_bytes"),
                           "percent": row.get("quota_used_percent"), "full_at": forecast["full_at"],
                           "status": "plein" if (row.get("quota_used_percent") or 0) >= 100 else "à surveiller" if row in watch else "ok"})
    return {
        "kpis": [
            _kpi("Volume mesuré", total, "bytes", f"{len(measured)} dossier(s) mesuré(s) sur {len(rows)}"),
            _kpi("Données de plus d'un an", _pct(cold1, total), "percent", f"dont {str(_pct(cold3, total) or 0).replace('.', ',')} % de plus de 3 ans",
                 "warn" if (_pct(cold1, total) or 0) > 50 else None),
            _kpi("Fichiers parasites", junk, "bytes", f"{sum(int(row.get('junk_files') or 0) for row in measured)} fichier(s)"),
            _kpi("Dossiers avec quota", len(with_quota), "int", f"{len(watch)} au-delà du seuil d'alerte", "warn" if watch else None),
        ],
        "sections": [
            {"title": "Par serveur", "columns": [_col("server", "Serveur"), _col("folders", "Dossiers", "int"), _col("bytes", "Volume", "bytes"),
                                                  _col("cold", "Plus d'un an", "bytes"), _col("quotas", "Avec quota", "int")],
             "rows": sorted(servers.values(), key=lambda entry: -entry["bytes"])},
            {"title": "Les plus gros dossiers", "columns": [_col("folder", "Dossier", "folder"), _col("bytes", "Volume", "bytes"),
                                                            _col("growth", "30 jours", "bytes"), _col("quota", "Quota", "percent")],
             "rows": [{"folder": _folder(row), "bytes": _size(row), "growth": row.get("growth_30d_bytes"), "quota": row.get("quota_used_percent")}
                      for row in _top(measured, _size)]},
            {"title": "Quotas", "description": "Remplissage et date où le quota sera plein au rythme actuel (après une semaine de mesures).",
             "columns": [_col("folder", "Dossier", "folder"), _col("used", "Utilisé", "bytes"), _col("limit", "Quota", "bytes"),
                         _col("percent", "Rempli", "percent"), _col("full_at", "Plein vers", "date"), _col("status", "État", "status")],
             "rows": sorted(quota_rows, key=lambda entry: -(entry["percent"] or 0)), "empty": "Aucun dossier n'a de quota."},
            {"title": "Données froides", "description": "Les dossiers où le plus de données n'ont pas été modifiées depuis plus de 3 ans.",
             "columns": [_col("folder", "Dossier", "folder"), _col("bytes", "Volume", "bytes"), _col("cold1", "Plus d'un an", "bytes"),
                         _col("cold3", "Plus de 3 ans", "bytes")],
             "rows": [{"folder": _folder(row), "bytes": _size(row), "cold1": row.get("cold_1y_bytes"), "cold3": row.get("cold_3y_bytes")}
                      for row in _top(measured, lambda r: float(r.get("cold_3y_bytes") or 0) + 0.001 * float(r.get("cold_1y_bytes") or 0))],
             "empty": "Aucune donnée de plus d'un an."},
            {"title": "Fichiers parasites", "columns": [_col("folder", "Dossier", "folder"), _col("files", "Fichiers", "int"), _col("bytes", "Volume", "bytes")],
             "rows": [{"folder": _folder(row), "files": row.get("junk_files"), "bytes": row.get("junk_bytes")}
                      for row in _top(measured, lambda r: float(r.get("junk_files") or 0))], "empty": "Aucun fichier parasite."},
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


def five_s_report(db: Session, rows: list[dict]) -> dict[str, Any]:
    result = five_s.compute(rows, five_s.scanned_at_by_root(db, [int(row.get("storage_root_id") or 0) for row in rows]))
    zones: dict[str, list[dict]] = {}
    for folder in result["folders"]:
        zones.setdefault(str(folder.get("zone") or "—"), []).append(folder)

    def avg(items: list[dict], pillar: str | None = None) -> int | None:
        values = [(f["pillars"].get(pillar) if pillar else f["score"]) for f in items]
        values = [v for v in values if v is not None]
        return round(sum(values) / len(values)) if values else None

    return {
        "kpis": [_kpi("Score 5S", result["score"], "score", f"{result['folders_count']} dossier(s)")]
                + [_kpi(five_s.LABELS[p], result["pillars"][p], "score") for p in five_s.PILLARS],
        "sections": [
            {"title": "Par zone", "columns": [_col("zone", "Zone"), _col("folders", "Dossiers", "int"), _col("score", "Score", "score"),
                                              *[_col(p, five_s.LABELS[p], "score") for p in five_s.PILLARS]],
             "rows": [{"zone": zone, "folders": len(items), "score": avg(items), **{p: avg(items, p) for p in five_s.PILLARS}}
                      for zone, items in sorted(zones.items())]},
            {"title": "Actions qui amélioreraient le plus le score", "columns": [_col("pillar", "Pilier"), _col("text", "Action"), _col("folders", "Dossiers", "int")],
             "rows": [{"pillar": five_s.LABELS[a["pillar"]], "text": a["text"], "folders": a["folders"]} for a in result["top_actions"]]},
            {"title": "Les 15 dossiers les moins bien tenus", "columns": [_col("folder", "Dossier", "folder"), _col("score", "Score", "score"),
                                                                           *[_col(p, five_s.LABELS[p], "score") for p in five_s.PILLARS]],
             "rows": [{"folder": {"id": f["id"], "name": f["name"], "path": f["path"]}, "score": f["score"], **f["pillars"]}
                      for f in result["folders"] if f["score"] is not None][:15]},
        ],
    }


def _iso(value: Any) -> str | None:
    return value.isoformat() + "Z" if isinstance(value, datetime) else value


BUILDERS = {"storage": storage, "security": security, "governance": governance, "five_s": five_s_report}


def build(db: Session, kind: str, rows: list[dict], scope: str) -> dict[str, Any]:
    title, description = KINDS[kind]
    return {"key": kind, "title": title, "description": description, "generated_at": _now().isoformat() + "Z", "scope": scope,
            **BUILDERS[kind](db, rows)}
