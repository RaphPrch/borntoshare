"""Same cases as frontend lib/components/storage-roots/folder-query.test.ts: one language, two sides."""
from __future__ import annotations

from app.services import folder_query as fq

ROWS = [
    {"storage_root_id": 1, "storage_root_name": "Finance", "root_path": "\\\\172.22.98.56\\PiloteB2S\\Finance", "zone_name": "CORP",
     "storage_endpoint_name": "FILER01", "tags": [{"label": "Données RH"}], "guardian_names": ["Alice Martin", "alice.martin"],
     "guardians_count": 1, "open_alerts_count": 0, "last_probe_status": "success", "content_size_bytes": 2 * 1024**3,
     "sensitive_files": 2, "dfs_path": "\\\\corp.local\\brest\\Corporate\\Finance"},
    {"storage_root_id": 2, "storage_root_name": "Archives", "root_path": "\\\\172.22.98.56\\Archives", "zone_name": "MAISON",
     "storage_endpoint_name": "FILER01", "tags": [], "guardian_names": [], "guardians_count": 0, "open_alerts_count": 3,
     "open_alert_types": "missing_guardian,acl_profile_missing", "last_probe_status": "failed", "content_size_bytes": 0,
     "inheritance_broken": True},
]


def ids(query: str) -> list[int]:
    return [row["storage_root_id"] for row in ROWS if fq.matches(row, query)]


def test_filters_and_free_text_are_separated():
    filters, text = fq.parse('compta tag:"Données RH" -est:alerte gardien:')
    assert text == "compta"
    assert [(f.key, f.value, f.neg) for f in filters] == [("tag", "Données RH", False), ("is", "alerte", True)]


def test_same_results_as_the_search_field():
    assert ids("tag:donnees") == [1]
    assert ids("gardien:alice") == [1]
    assert ids("g:martin zone:corp") == [1]
    assert ids("dfs:brest") == [1]
    assert ids("est:sans-gardien") == [2]
    assert ids("est:heritage-rompu") == [2]
    assert ids("est:injoignable") == [2]
    assert ids("-est:alerte") == [1]
    assert ids("alerte:acl") == [2]
    assert ids("taille>1Go") == [1]
    assert ids("taille<1Mo") == [2]
    assert ids("serveur:filer01 partage:archives") == [2]
    assert ids("est:sensible") == [1]
    assert ids("est:non-analyse") == [2]
    assert ids("archives") == [2]


def test_unknown_states_are_reported():
    assert fq.unknown_states("est:sensible est:sansgardien") == ["sansgardien"]


def test_new_sensitivity_states() -> None:
    row = {"personal_files": 2, "bank_files": 0, "risky_files": 1}
    assert fq.matches(row, "est:donnees-personnelles") and fq.matches(row, "est:fichiers-a-risque")
    assert not fq.matches(row, "est:bancaire") and not fq.matches({}, "est:donnees-personnelles")
    assert fq.unknown_states("est:donnees-personnelles est:bancaire est:fichiers-a-risque") == []


def test_path_matches_whole_words() -> None:
    rh = {"root_path": "\\\\172.22.98.56\\Lyon\\Lyon - RH"}
    archives = {"root_path": "\\\\172.22.98.56\\Archives\\Marhaba"}
    assert fq.matches(rh, "chemin:rh") and not fq.matches(archives, "chemin:rh")
    assert fq.matches({"root_path": "\\\\srv\\Siège\\Ressources humaines"}, 'chemin:"ressources humaines"')
    assert fq.matches({"root_path": "\\\\srv\\Data", "dfs_path": "\\\\corp.local\\brest\\Finance"}, "chemin:finance")
    assert fq.matches(rh, "-chemin:finance")


def test_duplicates_and_media_criteria():
    from app.services.folder_query import matches

    data = {"content_size_bytes": 659 * 1024**3, "dup_wasted_bytes": 102 * 1024**3, "media_bytes": 576 * 1024**3}
    assert matches(data, "doublons>10Go")
    assert not matches(data, "doublons>200Go")
    assert matches(data, "doublons<200Go")
    assert matches(data, "medias>50%")
    assert not matches(data, "medias>90%")
    assert matches(data, "medias>50")
    # Not measured: no criterion matches (never a false hit)
    assert not matches({"content_size_bytes": None}, "doublons>1Go")
    assert not matches({"content_size_bytes": 10, "media_bytes": None}, "medias>10%")
    assert not matches(data, "-medias>50%")
