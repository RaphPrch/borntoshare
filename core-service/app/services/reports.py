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

from app.services import folder_query
from app.core.values import utc_iso


# The reports of the core, each with what it needs: « core » always, « governance » the access governance, « fives » the
# 5S module (its sensitivity scan). The 5S and data hygiene reports (cold data, duplicates, clutter, growth) are served
# by the 5S module itself (fives-service).
KINDS = {
    "storage": ("Stockage et quotas", "Volume des dossiers, par serveur, les plus gros et leurs quotas.", "core"),
    "infrastructure": ("Disponibilité", "Dossiers joignables, injoignables, jamais testés ou dont la dernière collecte est ancienne, par serveur.", "core"),
    "alerts": ("Alertes ouvertes", "Alertes par type, par gravité et les dossiers qui en cumulent le plus.", "core"),
    "security": ("Sécurité des données", "Mots de passe et clés trouvés, données sensibles, corrections demandées.", "fives"),
    "governance": ("Gouvernance des accès", "Classement, quotas, demandes en attente et dossiers à revalider.", "governance"),
    "exposure": ("Exposition des dossiers", "Dossiers ouverts à toute l'entreprise, comptes hors BornToShare, héritage rompu.", "governance"),
    "guardians": ("Gardiens et suppléance", "Dossiers sans gardien, sans suppléant, et la charge de chaque gardien.", "governance"),
    "requests": ("Activité des demandes d'accès", "Demandes de la période : décidées, refusées, en attente, en échec, délai de décision.", "governance"),
}
LICENSES = ("core", "governance", "fives")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _col(key: str, label: str, type_: str = "text") -> dict[str, str]:
    return {"key": key, "label": label, "type": type_}


def _status(text: str, tone: str | None) -> dict[str, Any]:
    """A cell of a « status » column: its words and its colour (ok, warn, bad), said by the core rather than guessed
    from the words by the page."""
    return {"text": text, "tone": tone}


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


def storage(db: Session, rows: list[dict], ctx: dict | None = None) -> dict[str, Any]:
    measured = [row for row in rows if row.get("content_size_bytes") is not None]
    total = sum(_size(row) for row in measured)
    with_quota = [row for row in rows if row.get("quota_limit_bytes") is not None]
    # The rules of the express search (est:…): the report lists what « See » lists in Storage Roots
    watch = [row for row in with_quota if folder_query.STATES["quota-plein"](row)]
    servers: dict[str, dict[str, Any]] = {}
    for row in measured:
        entry = servers.setdefault(str(row.get("storage_endpoint_name") or "—"), {"server": str(row.get("storage_endpoint_name") or "—"),
                                                                                  "folders": 0, "bytes": 0, "files": 0, "quotas": 0})
        entry["folders"] += 1
        entry["bytes"] += _size(row)
        entry["files"] += int(row.get("content_files") or 0)
        entry["quotas"] += 1 if row.get("quota_limit_bytes") is not None else 0
    quota_rows = [{"folder": _folder(row), "used": row.get("quota_used_bytes"), "limit": row.get("quota_limit_bytes"), "percent": row.get("quota_used_percent"),
                   "status": _status("plein", "bad") if (row.get("quota_used_percent") or 0) >= 100
                   else _status("à surveiller", "warn") if row in watch else _status("ok", "ok")} for row in with_quota]
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


# Reports of the access governance only: not listed nor served on a 5S-only installation
GOVERNANCE_KINDS = {"governance"}


def kinds(governance: bool, fives: bool = False) -> dict[str, tuple[str, str, str]]:
    """The reports this installation serves: those whose license is on."""
    on = {"core", *(["governance"] if governance else []), *(["fives"] if fives else [])}
    return {key: value for key, value in KINDS.items() if value[2] in on}


def security(db: Session, rows: list[dict], ctx: dict | None = None) -> dict[str, Any]:
    ids = [int(row.get("storage_root_id") or 0) for row in rows]
    by_id = {int(row.get("storage_root_id") or 0): row for row in rows}
    scanned = [row for row in rows if row.get("sensitive_files") is not None]
    with_pw = [row for row in rows if folder_query.STATES["mot-de-passe"](row)]
    with_keys = [row for row in rows if folder_query.STATES["cle-ou-jeton"](row)]
    corrections = []
    if ids:
        corrections = [dict(row) for row in db.execute(
            text("SELECT storage_root_id, status, files_at_request, requested_by, requested_at, due_at, closed_at FROM sensitivity_remediations "
                 "WHERE storage_root_id IN :ids AND requested_at >= :since ORDER BY requested_at DESC").bindparams(bindparam("ids", expanding=True)),
            {"ids": ids, "since": _now() - timedelta(days=90)},
        ).mappings().all()]
    labels = {"open": "en cours", "overdue": "en retard", "done": "corrigée", "cancelled": "annulée"}
    tones = {"open": "warn", "overdue": "bad", "done": "ok", "cancelled": None}

    def correction(code: Any) -> dict[str, Any]:
        if not code:
            return _status("non demandée", "bad")
        return _status(labels.get(str(code), str(code)), tones.get(str(code)))

    personal = [row for row in rows if folder_query.STATES["donnees-personnelles"](row) or folder_query.STATES["bancaire"](row)]
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
                       "correction": correction(row.get("remediation_status"))}
                      for row in sorted({id(r): r for r in [*with_pw, *with_keys]}.values(),
                                        key=lambda r: -(int(r.get("password_files") or 0) + int(r.get("key_files") or 0)))],
             "empty": "Aucun mot de passe ni aucune clé trouvés."},
            {"title": "Données personnelles et bancaires", "columns": [_col("folder", "Dossier", "folder"), _col("personal", "Personnelles", "int"),
                                                                        _col("bank", "Bancaires", "int"), _col("risky", "Fichiers à risque", "int")],
             "rows": [{"folder": _folder(row), "personal": row.get("personal_files"), "bank": row.get("bank_files"), "risky": row.get("risky_files")}
                      for row in sorted(personal, key=lambda r: -(int(r.get("personal_files") or 0) + int(r.get("bank_files") or 0)))],
             "empty": "Aucune donnée personnelle ni bancaire trouvée."},
            {"title": "Corrections des 90 derniers jours", "columns": [_col("folder", "Dossier", "folder"), _col("status", "État", "status"),
                                                                       _col("files", "Fichiers", "int"), _col("requested_at", "Demandée", "date"),
                                                                       _col("due_at", "Échéance", "date"), _col("closed_at", "Close", "date")],
             "rows": [{"folder": _folder(by_id.get(int(c["storage_root_id"]), {"storage_root_id": c["storage_root_id"]})), "status": correction(c["status"]),
                       "files": c["files_at_request"], "requested_at": utc_iso(c["requested_at"]), "due_at": utc_iso(c["due_at"]), "closed_at": utc_iso(c["closed_at"])}
                      for c in corrections], "empty": "Aucune correction demandée."},
        ],
    }


def governance(db: Session, rows: list[dict], ctx: dict | None = None) -> dict[str, Any]:
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


def infrastructure(db: Session, rows: list[dict], ctx: dict | None = None) -> dict[str, Any]:
    """Can BornToShare reach the folders, and how fresh is what it knows (the last probe of each folder)."""
    stale_before = (ctx or {}).get("stale_before") or (_now() - timedelta(hours=12))
    unreachable = [row for row in rows if folder_query.STATES["injoignable"](row)]
    never = [row for row in rows if folder_query.STATES["non-teste"](row)]
    stale = [row for row in rows if row.get("last_probe_at") and _when(row["last_probe_at"]) and _when(row["last_probe_at"]) < stale_before]
    servers: dict[str, dict[str, Any]] = {}
    for row in rows:
        name = str(row.get("storage_endpoint_name") or "—")
        entry = servers.setdefault(name, {"server": name, "folders": 0, "unreachable": 0, "never": 0, "stale": 0, "last": None})
        entry["folders"] += 1
        entry["unreachable"] += 1 if row in unreachable else 0
        entry["never"] += 1 if row in never else 0
        entry["stale"] += 1 if row in stale else 0
        when = utc_iso(_when(row.get("last_probe_at")))
        entry["last"] = max(filter(None, [entry["last"], when]), default=None)
    reachable = len(rows) - len(unreachable) - len(never)
    return {
        "kpis": [
            _kpi("Dossiers joignables", _pct(reachable, len(rows)), "percent", f"{reachable} sur {len(rows)}", "ok" if not unreachable else "warn"),
            _kpi("Injoignables", len(unreachable), "int", None, "bad" if unreachable else "ok"),
            _kpi("Jamais testés", len(never), "int", None, "warn" if never else None),
            _kpi("Collecte ancienne", len(stale), "int", "plus de deux cycles de synchronisation", "warn" if stale else None),
        ],
        "sections": [
            {"title": "Par serveur", "columns": [_col("server", "Serveur"), _col("folders", "Dossiers", "int"), _col("unreachable", "Injoignables", "int"),
                                                  _col("never", "Jamais testés", "int"), _col("stale", "Collecte ancienne", "int"), _col("last", "Dernière collecte", "date")],
             "rows": sorted(servers.values(), key=lambda entry: (-entry["unreachable"], entry["server"]))},
            {"title": "Dossiers injoignables", "columns": [_col("folder", "Dossier", "folder"), _col("server", "Serveur"), _col("message", "Dernier message"),
                                                          _col("last", "Dernier test", "date")],
             "rows": [{"folder": _folder(row), "server": row.get("storage_endpoint_name"), "message": row.get("last_probe_message"),
                       "last": utc_iso(_when(row.get("last_probe_at")))} for row in unreachable], "empty": "Tous les dossiers testés répondent."},
            {"title": "Jamais testés", "columns": [_col("folder", "Dossier", "folder"), _col("server", "Serveur")],
             "rows": [{"folder": _folder(row), "server": row.get("storage_endpoint_name")} for row in never], "empty": "Tous les dossiers ont été testés."},
        ],
    }


def alerts(db: Session, rows: list[dict], ctx: dict | None = None) -> dict[str, Any]:
    """The open alerts of these folders: by type, by severity, the folders that pile them up, the serious ones."""
    by_id = {int(row.get("storage_root_id") or 0): row for row in rows}
    found = [dict(row) for row in db.execute(
        text("SELECT storage_root_id, alert_type, severity, title, last_seen_at FROM governance_alerts "
             "WHERE status = 'open' AND storage_root_id IN :ids ORDER BY last_seen_at DESC").bindparams(bindparam("ids", expanding=True)),
        {"ids": sorted(by_id) or [0]},
    ).mappings().all()] if by_id else []
    serious = [a for a in found if a["severity"] in {"critical", "high"}]
    types: dict[str, dict[str, Any]] = {}
    per_folder: dict[int, int] = {}
    for alert in found:
        entry = types.setdefault(str(alert["alert_type"]), {"type": str(alert["title"] or alert["alert_type"]), "count": 0, "serious": 0, "folders": set()})
        entry["count"] += 1
        entry["serious"] += 1 if alert in serious else 0
        entry["folders"].add(int(alert["storage_root_id"]))
        per_folder[int(alert["storage_root_id"])] = per_folder.get(int(alert["storage_root_id"]), 0) + 1
    severity = {"critical": _status("critique", "bad"), "high": _status("élevée", "bad"), "warning": _status("avertissement", "warn"),
                "info": _status("information", None)}
    return {
        "kpis": [
            _kpi("Alertes ouvertes", len(found), "int", f"dans {len(per_folder)} dossier(s)", "warn" if found else "ok"),
            _kpi("Critiques ou élevées", len(serious), "int", None, "bad" if serious else "ok"),
            _kpi("Types d'alerte", len(types), "int"),
        ],
        "sections": [
            {"title": "Par type", "columns": [_col("type", "Type"), _col("count", "Alertes", "int"), _col("serious", "Graves", "int"), _col("folders", "Dossiers", "int")],
             "rows": sorted(({**entry, "folders": len(entry["folders"])} for entry in types.values()), key=lambda entry: -entry["count"]),
             "empty": "Aucune alerte ouverte."},
            {"title": "Dossiers les plus concernés", "columns": [_col("folder", "Dossier", "folder"), _col("count", "Alertes", "int")],
             "rows": [{"folder": _folder(by_id[rid]), "count": count} for rid, count in sorted(per_folder.items(), key=lambda item: -item[1])[:20]],
             "empty": "Aucune alerte ouverte."},
            {"title": "Alertes graves", "columns": [_col("folder", "Dossier", "folder"), _col("title", "Alerte"), _col("severity", "Gravité", "status"),
                                                    _col("seen", "Vue", "date")],
             "rows": [{"folder": _folder(by_id[int(a["storage_root_id"])]), "title": a["title"] or a["alert_type"], "severity": severity.get(a["severity"], _status(str(a["severity"]), None)),
                       "seen": utc_iso(a["last_seen_at"])} for a in serious[:200]], "empty": "Aucune alerte critique ni élevée."},
        ],
    }


def exposure(db: Session, rows: list[dict], ctx: dict | None = None) -> dict[str, Any]:
    """How widely the last ACL read opens each folder (the exposure map), restricted to these folders."""
    from app.services.exposure import build_exposure

    by_id = {int(row.get("storage_root_id") or 0): row for row in rows}
    data = build_exposure(db, set(by_id))
    folders = [folder for zone in data["zones"] for server in zone["servers"] for share in server["shares"] for folder in share["folders"]]
    opened = [f for f in folders if f["level"] in {"open_write", "open_read"}]
    outside = [f for f in folders if f["level"] == "outside"]
    broken = [row for row in rows if folder_query.STATES["heritage-rompu"](row)]
    summary = data["summary"]
    read = int(summary["total"]) - int(summary["unknown"])
    rights = {"full": "contrôle total", "modify": "modification", "read": "lecture", "special": "spéciaux"}
    return {
        "kpis": [
            _kpi("Gouvernés", _pct(int(summary["governed"]), read), "percent", f"{summary['governed']} sur {read} lus", "ok" if not opened else "warn"),
            _kpi("Ouverts à tous en modification", int(summary["open_write"]), "int", None, "bad" if summary["open_write"] else "ok"),
            _kpi("Ouverts à tous en lecture", int(summary["open_read"]), "int", None, "warn" if summary["open_read"] else None),
            _kpi("Comptes hors BornToShare", int(summary["outside"]), "int", "dossiers concernés", "warn" if summary["outside"] else None),
        ],
        "sections": [
            {"title": "Ouverts à toute l'entreprise", "columns": [_col("folder", "Dossier", "folder"), _col("who", "Ouvert à"), _col("rights", "Droit"),
                                                                 _col("inherited", "Hérité")],
             "rows": [{"folder": _folder(by_id.get(f["id"], {"storage_root_id": f["id"], "storage_root_name": f["name"]})),
                       "who": ", ".join(b["principal"] for b in f["broad"]), "rights": ", ".join(sorted({rights.get(b["rights"], b["rights"]) for b in f["broad"]})),
                       "inherited": "oui" if any(b["inherited"] for b in f["broad"]) else "non"}
                      for f in sorted(opened, key=lambda f: f["level"] != "open_write")], "empty": "Aucun dossier ouvert à tous."},
            {"title": "Comptes hors BornToShare", "description": "Comptes ou groupes posés directement sur le serveur, hors des groupes gérés.",
             "columns": [_col("folder", "Dossier", "folder"), _col("count", "Comptes", "int")],
             "rows": [{"folder": _folder(by_id.get(f["id"], {"storage_root_id": f["id"], "storage_root_name": f["name"]})), "count": f["outside_count"]}
                      for f in sorted(outside, key=lambda f: -f["outside_count"])], "empty": "Aucun compte hors BornToShare."},
            {"title": "Héritage rompu", "columns": [_col("folder", "Dossier", "folder")], "rows": [{"folder": _folder(row)} for row in broken],
             "empty": "Aucun dossier à l'héritage rompu."},
        ],
    }


def guardians(db: Session, rows: list[dict], ctx: dict | None = None) -> dict[str, Any]:
    """Who answers for the folders: without guardian, one guardian without backup, and how many folders each one holds."""
    without = [row for row in rows if folder_query.STATES["sans-gardien"](row)]
    no_backup = [row for row in rows if folder_query.STATES["sans-suppleant"](row)]
    load: dict[str, int] = {}
    for row in rows:
        for name in _guardian_names(row):
            load[name] = load.get(name, 0) + 1
    return {
        "kpis": [
            _kpi("Avec gardien", _pct(len(rows) - len(without), len(rows)), "percent", f"{len(rows) - len(without)} sur {len(rows)}", "warn" if without else "ok"),
            _kpi("Sans gardien", len(without), "int", "leurs demandes vont aux administrateurs", "bad" if without else "ok"),
            _kpi("Sans suppléant", len(no_backup), "int", "une absence bloque les décisions", "warn" if no_backup else None),
            _kpi("Gardiens", len(load), "int"),
        ],
        "sections": [
            {"title": "Sans gardien", "columns": [_col("folder", "Dossier", "folder"), _col("server", "Serveur")],
             "rows": [{"folder": _folder(row), "server": row.get("storage_endpoint_name")} for row in without], "empty": "Tous les dossiers ont un gardien."},
            {"title": "Un seul gardien, sans suppléant", "columns": [_col("folder", "Dossier", "folder"), _col("guardian", "Gardien")],
             "rows": [{"folder": _folder(row), "guardian": ", ".join(_guardian_names(row))} for row in no_backup], "empty": "Chaque dossier gardé a un relais."},
            {"title": "Charge des gardiens", "columns": [_col("guardian", "Gardien"), _col("folders", "Dossiers", "int")],
             "rows": [{"guardian": name, "folders": count} for name, count in sorted(load.items(), key=lambda item: (-item[1], item[0]))],
             "empty": "Aucun gardien."},
        ],
    }


def _guardian_names(row: dict) -> list[str]:
    """One name per guardian (the « guardians » entries of the folder list)."""
    return [str(g.get("name") or g.get("login")) for g in (row.get("guardians") or []) if isinstance(g, dict) and (g.get("name") or g.get("login"))]


def requests(db: Session, rows: list[dict], ctx: dict | None = None) -> dict[str, Any]:
    """The access requests of the period on these folders: what was decided, how fast, what waits, what failed."""
    days = int((ctx or {}).get("days") or 30)
    by_id = {int(row.get("storage_root_id") or 0): row for row in rows}
    since = _now() - timedelta(days=days)
    found = [dict(row) for row in db.execute(
        text("""SELECT v.request_id, v.request_code, v.status, v.created_at, v.storage_root_id, v.requested_for_display, v.latest_execution_status,
                       ar.decided_at
                FROM v_access_requests v LEFT JOIN access_requests ar ON ar.id = v.request_id
                WHERE v.storage_root_id IN :ids AND v.created_at >= :since ORDER BY v.created_at DESC""").bindparams(bindparam("ids", expanding=True)),
        {"ids": sorted(by_id) or [0], "since": since},
    ).mappings().all()] if by_id else []
    for r in found:
        r["status"] = str(r["status"] or "").lower()
    approved = [r for r in found if r["status"] in {"approved", "expired", "revoked"}]
    rejected = [r for r in found if r["status"] == "rejected"]
    pending = [r for r in found if r["status"] == "pending"]
    failed = [r for r in found if r["status"] == "failed" or str(r["latest_execution_status"] or "").upper() in {"FAILED", "ERROR", "TIMED_OUT"}]
    delays = sorted((r["decided_at"] - r["created_at"]).total_seconds() / 86400 for r in found
                    if isinstance(r.get("decided_at"), datetime) and isinstance(r.get("created_at"), datetime) and r["decided_at"] >= r["created_at"])
    median = delays[len(delays) // 2] if delays else None
    per_folder: dict[int, dict[str, Any]] = {}
    for r in found:
        entry = per_folder.setdefault(int(r["storage_root_id"]), {"folder": _folder(by_id[int(r["storage_root_id"])]), "total": 0, "approved": 0,
                                                                   "rejected": 0, "pending": 0})
        entry["total"] += 1
        entry["approved"] += 1 if r in approved else 0
        entry["rejected"] += 1 if r in rejected else 0
        entry["pending"] += 1 if r in pending else 0
    return {
        "period_days": days,
        "kpis": [
            _kpi("Demandes", len(found), "int", f"sur {days} jours"),
            _kpi("Accordées", len(approved), "int", f"{len(rejected)} refusée(s)"),
            _kpi("En attente", len(pending), "int", None, "warn" if pending else None),
            _kpi("En échec", len(failed), "int", "non appliquées sur le serveur ou l'annuaire", "bad" if failed else "ok"),
            _kpi("Délai médian de décision", round(median, 1) if median is not None else None, "int", "jours"),
        ],
        "sections": [
            {"title": "Par dossier", "columns": [_col("folder", "Dossier", "folder"), _col("total", "Demandes", "int"), _col("approved", "Accordées", "int"),
                                                  _col("rejected", "Refusées", "int"), _col("pending", "En attente", "int")],
             "rows": sorted(per_folder.values(), key=lambda entry: -entry["total"])[:50], "empty": "Aucune demande sur la période."},
            {"title": "En échec", "columns": [_col("code", "Demande"), _col("folder", "Dossier", "folder"), _col("who", "Pour"), _col("created", "Créée", "date")],
             "rows": [{"code": r["request_code"], "folder": _folder(by_id[int(r["storage_root_id"])]), "who": r["requested_for_display"],
                       "created": utc_iso(r["created_at"])} for r in failed[:200]], "empty": "Aucune demande en échec."},
        ],
    }


def _when(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None) if value else None
    except ValueError:
        return None


BUILDERS = {"storage": storage, "infrastructure": infrastructure, "alerts": alerts, "security": security, "governance": governance,
            "exposure": exposure, "guardians": guardians, "requests": requests}


def build(db: Session, kind: str, rows: list[dict], scope: str, governance_on: bool = True, fives_on: bool = False, **ctx: Any) -> dict[str, Any]:
    title, description, license_ = kinds(governance_on, fives_on)[kind]
    body = BUILDERS[kind](db, rows, {"governance": governance_on, "fives": fives_on, **ctx})
    return {"key": kind, "title": title, "description": description, "license": license_, "generated_at": _now().isoformat() + "Z",
            "scope": scope, **body}
