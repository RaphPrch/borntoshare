"""Reports of the module, in the same shape as the reports of the core (one page shows them all):
  {key, title, description, generated_at, scope, kpis: [...], sections: [{title, description, columns, rows, empty}]}
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services import five_s

KINDS = {
    "fives-5s": ("5S des partages", "Score 5S des dossiers, par pilier et par zone, et les actions qui l'amélioreraient."),
    "fives-hygiene": ("Hygiène des données", "Données froides, doublons, fichiers parasites et croissance des dossiers."),
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


def _top(rows: list[dict], key, limit: int = 10) -> list[dict]:
    return sorted([row for row in rows if key(row) > 0], key=key, reverse=True)[:limit]


def five_s_report(rows: list[dict]) -> dict[str, Any]:
    result = five_s.compute(rows)
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


def hygiene_report(rows: list[dict], between: dict[str, int]) -> dict[str, Any]:
    measured = [row for row in rows if row.get("content_size_bytes") is not None]
    total = sum(_size(row) for row in measured)
    cold1 = sum(int(row.get("cold_1y_bytes") or 0) for row in measured)
    cold3 = sum(int(row.get("cold_3y_bytes") or 0) for row in measured)
    junk = sum(int(row.get("junk_bytes") or 0) for row in measured)
    inside = sum(int(row.get("dup_wasted_bytes") or 0) for row in measured)
    growing = _top(measured, lambda r: float(r.get("growth_30d_bytes") or 0))
    return {
        "kpis": [
            _kpi("Données de plus d'un an", _pct(cold1, total), "percent", f"dont {str(_pct(cold3, total) or 0).replace('.', ',')} % de plus de 3 ans",
                 "warn" if (_pct(cold1, total) or 0) > 50 else None),
            _kpi("Doublons à libérer", inside + between["bytes"], "bytes",
                 f"dans les dossiers {five_s._bytes(inside)} · entre dossiers {five_s._bytes(between['bytes'])}", "warn" if inside + between["bytes"] else None),
            _kpi("Fichiers parasites", junk, "bytes", f"{sum(int(row.get('junk_files') or 0) for row in measured)} fichier(s)"),
            _kpi("Volume mesuré", total, "bytes", f"{len(measured)} dossier(s) mesuré(s) sur {len(rows)}"),
        ],
        "sections": [
            {"title": "Données froides", "description": "Les dossiers où le plus de données n'ont pas été modifiées depuis plus de 3 ans.",
             "columns": [_col("folder", "Dossier", "folder"), _col("bytes", "Volume", "bytes"), _col("cold1", "Plus d'un an", "bytes"),
                         _col("cold3", "Plus de 3 ans", "bytes")],
             "rows": [{"folder": _folder(row), "bytes": _size(row), "cold1": row.get("cold_1y_bytes"), "cold3": row.get("cold_3y_bytes")}
                      for row in _top(measured, lambda r: float(r.get("cold_3y_bytes") or 0) + 0.001 * float(r.get("cold_1y_bytes") or 0))],
             "empty": "Aucune donnée de plus d'un an."},
            {"title": "Doublons", "description": "Copies probables (même taille et même empreinte) dans un dossier, ou présentes aussi dans d'autres dossiers.",
             "columns": [_col("folder", "Dossier", "folder"), _col("inside", "Dans le dossier", "bytes"), _col("groups", "Groupes", "int"),
                         _col("shared", "Aussi ailleurs", "bytes"), _col("with", "Autres dossiers", "int")],
             "rows": [{"folder": _folder(row), "inside": row.get("dup_wasted_bytes"), "groups": row.get("dup_groups"),
                       "shared": row.get("shared_dup_bytes"), "with": row.get("shared_dup_folders")}
                      for row in _top(measured, lambda r: float(r.get("dup_wasted_bytes") or 0) + float(r.get("shared_dup_bytes") or 0))],
             "empty": "Aucun doublon trouvé (les doublons demandent une mesure sur le serveur Windows)."},
            {"title": "Fichiers parasites", "columns": [_col("folder", "Dossier", "folder"), _col("files", "Fichiers", "int"), _col("bytes", "Volume", "bytes")],
             "rows": [{"folder": _folder(row), "files": row.get("junk_files"), "bytes": row.get("junk_bytes")}
                      for row in _top(measured, lambda r: float(r.get("junk_files") or 0))], "empty": "Aucun fichier parasite."},
            {"title": "Les dossiers qui grossissent le plus", "description": "Sur 30 jours, d'après l'historique des mesures du module.",
             "columns": [_col("folder", "Dossier", "folder"), _col("bytes", "Volume", "bytes"), _col("growth", "30 jours", "bytes"),
                         _col("quota", "Quota", "percent")],
             "rows": [{"folder": _folder(row), "bytes": _size(row), "growth": row.get("growth_30d_bytes"), "quota": row.get("quota_used_percent")}
                      for row in growing], "empty": "Pas encore assez de mesures pour une tendance."},
        ],
    }


def build(kind: str, rows: list[dict], scope: str, between: dict[str, int] | None = None) -> dict[str, Any]:
    title, description = KINDS[kind]
    body = five_s_report(rows) if kind == "fives-5s" else hygiene_report(rows, between or {"bytes": 0, "files": 0})
    return {"key": kind, "title": title, "description": description, "generated_at": _now().isoformat() + "Z", "scope": scope, **body}
