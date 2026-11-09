"""5S of the file shares: the lean method applied to the governed folders, from what BornToShare already knows.

Each folder gets a score out of 100 per pillar, and the actions that would raise it:
- Trier (Seiri, sort): keep what is used. Data untouched for 1 to 3 years weighs half, over 3 years fully.
- Ranger (Seiton, set in order): each folder has its owners and its place: enough guardians, a tag, a quota.
- Nettoyer (Seiso, shine): nothing that should not be there: passwords, keys and tokens, clutter files.
- Standardiser (Seiketsu): the folder follows the rule: inheritance as expected, no error alert, reachable.
- Respecter (Shitsuke, sustain): it is kept up: measured and scanned recently, corrections and requests handled.
A pillar without the data to judge it (never measured, never scanned) gives no score rather than a wrong one.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

PILLARS = ("sort", "order", "shine", "standard", "sustain")
LABELS = {"sort": "Trier", "order": "Ranger", "shine": "Nettoyer", "standard": "Standardiser", "sustain": "Respecter"}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _size(row: dict) -> int | None:
    value = row.get("content_size_bytes")
    return None if value in (None, "") else int(value)


def _bytes(value: float) -> str:
    for unit in ("o", "Ko", "Mo", "Go", "To"):
        if value < 1024 or unit == "To":
            return f"{value:.1f} {unit}".replace(".0 ", " ").replace(".", ",")
        value /= 1024
    return str(value)


def scanned_at_by_root(db: Session, ids: list[int]) -> dict[int, datetime]:
    if not ids:
        return {}
    try:
        rows = db.execute(
            text("SELECT storage_root_id, scanned_at FROM storage_root_sensitivity WHERE scanned_at IS NOT NULL AND storage_root_id IN :ids")
            .bindparams(bindparam("ids", expanding=True)),
            {"ids": ids},
        ).all()
    except Exception:
        db.rollback()
        return {}
    return {int(root_id): at for root_id, at in rows}


def score_folder(row: dict, scanned_at: datetime | None, now: datetime | None = None) -> dict[str, Any]:
    now = now or _now()
    pillars: dict[str, int | None] = {}
    actions: list[dict[str, str]] = []
    size = _size(row)

    # Trier: cold data and duplicates (inside the folder fully, shared with other folders half: one copy may be the right one)
    if size and row.get("cold_1y_bytes") is not None:
        cold1, cold3 = int(row.get("cold_1y_bytes") or 0), int(row.get("cold_3y_bytes") or 0)
        dup, shared = int(row.get("dup_wasted_bytes") or 0), int(row.get("shared_dup_bytes") or 0)
        weight = min(1.0, (cold3 + 0.5 * (cold1 - cold3) + dup + 0.5 * shared) / size)
        pillars["sort"] = max(0, round(100 * (1 - weight)))
        if dup:
            actions.append({"pillar": "sort", "text": f"Supprimer {_bytes(dup)} de doublons dans le dossier ({int(row.get('dup_groups') or 0)} groupe(s))"})
        if shared:
            actions.append({"pillar": "sort", "text": f"Dédoublonner {_bytes(shared)} présents aussi dans {int(row.get('shared_dup_folders') or 0)} autre(s) dossier(s)"})
        if cold3:
            actions.append({"pillar": "sort", "text": f"Archiver {_bytes(cold3)} non modifiés depuis plus de 3 ans"})
        elif cold1 > 0.3 * size:
            actions.append({"pillar": "sort", "text": f"Revoir {_bytes(cold1)} non modifiés depuis plus d'un an"})
    else:
        pillars["sort"] = None

    # Ranger: guardians, tag, quota
    order = 0
    if int(row.get("guardians_count") or 0) >= 2:
        order += 40
    elif int(row.get("guardians_count") or 0) == 1:
        order += 20
        actions.append({"pillar": "order", "text": "Ajouter un second gardien (un seul aujourd'hui)"})
    else:
        actions.append({"pillar": "order", "text": "Nommer des gardiens"})
    if row.get("tags"):
        order += 30
    else:
        actions.append({"pillar": "order", "text": "Classer le dossier avec un tag"})
    if row.get("quota_limit_bytes") is not None:
        order += 30
    else:
        actions.append({"pillar": "order", "text": "Définir un quota"})
    pillars["order"] = order

    # Nettoyer: passwords, keys, clutter (needs a scan or a measure)
    if row.get("sensitive_files") is None and row.get("junk_files") is None:
        pillars["shine"] = None
    else:
        shine = 100
        if int(row.get("password_files") or 0):
            shine -= 50
            status = row.get("remediation_status")
            actions.append({"pillar": "shine", "text": "Correction des mots de passe en retard" if status == "overdue"
                            else "Correction des mots de passe en cours" if status == "open"
                            else f"Retirer les mots de passe ({int(row['password_files'])} fichier(s))"})
        if int(row.get("key_files") or 0):
            shine -= 30
            actions.append({"pillar": "shine", "text": f"Retirer les clés et jetons ({int(row['key_files'])} fichier(s))"})
        junk = int(row.get("junk_files") or 0)
        if junk:
            shine -= min(20, junk)
            actions.append({"pillar": "shine", "text": f"Supprimer {junk} fichier(s) parasite(s) ({_bytes(int(row.get('junk_bytes') or 0))})"})
        pillars["shine"] = max(0, shine)

    # Standardiser: inheritance, error alerts, reachable
    standard = 0
    if row.get("inheritance_broken") is not True:
        standard += 40
    else:
        actions.append({"pillar": "standard", "text": "Vérifier l'héritage rompu du dossier"})
    if int(row.get("open_alerts_error_count") or 0) == 0:
        standard += 30
    else:
        actions.append({"pillar": "standard", "text": f"Traiter {int(row['open_alerts_error_count'])} alerte(s) en erreur"})
    if row.get("last_probe_status") == "success":
        standard += 30
    else:
        actions.append({"pillar": "standard", "text": "Tester le dossier (accès du serveur)"})
    pillars["standard"] = standard

    # Respecter: kept up over time
    sustain = 0
    measured = _parse(row.get("content_updated_at"))
    if measured and now - measured <= timedelta(days=30):
        sustain += 25
    else:
        actions.append({"pillar": "sustain", "text": "Mesurer le dossier (dernière mesure de plus de 30 jours)" if measured else "Mesurer le dossier"})
    if scanned_at and now - scanned_at <= timedelta(days=90):
        sustain += 25
    else:
        actions.append({"pillar": "sustain", "text": "Relancer l'analyse de sensibilité" if scanned_at else "Lancer l'analyse de sensibilité"})
    sustain += {None: 25, "open": 15}.get(row.get("remediation_status"), 0)
    if int(row.get("pending_validation_count") or 0) == 0 and int(row.get("quota_pending_requests") or 0) == 0:
        sustain += 25
    else:
        actions.append({"pillar": "sustain", "text": "Décider les demandes en attente"})
    pillars["sustain"] = sustain

    known = [value for value in pillars.values() if value is not None]
    return {"score": round(sum(known) / len(known)) if known else None, "pillars": pillars, "actions": actions}


def compute(rows: list[dict[str, Any]], scanned: dict[int, datetime]) -> dict[str, Any]:
    now = _now()
    folders = []
    for row in rows:
        root_id = int(row.get("storage_root_id") or 0)
        result = score_folder(row, scanned.get(root_id), now)
        folders.append({
            "id": root_id, "name": row.get("storage_root_name"), "path": row.get("dfs_path") or row.get("root_path"),
            "server": row.get("storage_endpoint_name"), "zone": row.get("zone_name"), "zone_id": row.get("zone_id"),
            "size_bytes": _size(row), **result,
        })
    averages: dict[str, int | None] = {}
    for pillar in PILLARS:
        values = [f["pillars"][pillar] for f in folders if f["pillars"].get(pillar) is not None]
        averages[pillar] = round(sum(values) / len(values)) if values else None
    scores = [f["score"] for f in folders if f["score"] is not None]
    # The actions that would help the most folders, first
    counts: dict[tuple[str, str], int] = {}
    for folder in folders:
        for action in folder["actions"]:
            key = (action["pillar"], _family(action["text"]))
            counts[key] = counts.get(key, 0) + 1
    top_actions = [{"pillar": pillar, "text": label, "folders": count}
                   for (pillar, label), count in sorted(counts.items(), key=lambda item: -item[1])[:8]]
    return {
        "score": round(sum(scores) / len(scores)) if scores else None,
        "pillars": averages,
        "labels": LABELS,
        "folders_count": len(folders),
        "top_actions": top_actions,
        "folders": sorted(folders, key=lambda f: (f["score"] is None, f["score"] if f["score"] is not None else 0)),
    }


def _family(text_value: str) -> str:
    """« Archiver 2 Go non modifiés… » → « Archiver les données de plus de 3 ans »: the same action across folders."""
    families = (
        ("Dédoublonner", "Dédoublonner entre dossiers"),
        ("Archiver", "Archiver les données de plus de 3 ans"), ("Revoir", "Revoir les données de plus d'un an"),
        ("Ajouter un second gardien", "Ajouter un second gardien"), ("Nommer des gardiens", "Nommer des gardiens"),
        ("Classer", "Classer avec un tag"), ("Définir un quota", "Définir un quota"),
        ("Correction des mots de passe en retard", "Corrections de mots de passe en retard"),
        ("Correction des mots de passe en cours", "Corrections de mots de passe en cours"),
        ("Retirer les mots de passe", "Retirer les mots de passe"), ("Retirer les clés", "Retirer les clés et jetons"),
        ("Supprimer", "Supprimer les fichiers parasites"), ("Vérifier l'héritage", "Vérifier l'héritage rompu"),
        ("Traiter", "Traiter les alertes en erreur"), ("Tester", "Tester les dossiers"),
        ("Mesurer", "Mesurer les dossiers"), ("Relancer", "Relancer l'analyse de sensibilité"),
        ("Lancer", "Lancer l'analyse de sensibilité"), ("Décider", "Décider les demandes en attente"),
    )
    if text_value.startswith("Supprimer") and "doublons" in text_value:
        return "Supprimer les doublons dans les dossiers"
    for prefix, family in families:
        if text_value.startswith(prefix):
            return family
    return text_value
