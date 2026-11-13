"""Tags of the sub-folders of a governed folder, set by the smart policies « also on the sub-folders ».

A sub-folder is judged on what is known of it without walking it again:
- its own name, for « chemin:… » (chemin:irm tags DATA\\Images IRM, not every folder below it);
- the files found right in it by the sensitivity scan, for « est:mot-de-passe », « est:donnees-personnelles »…
Other criteria (size, duplicates, cold data) stay on the governed folder. Paths are kept from the share, as the
measures and the 5S explorer keep them.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.services import folder_query

logger = logging.getLogger(__name__)

# « est:… » values a sub-folder can be judged on, and the categories of the sensitivity scan behind them
STATE_CATEGORIES: dict[str, tuple[str, ...]] = {}


def _categories() -> dict[str, tuple[str, ...]]:
    if not STATE_CATEGORIES:
        from app.services import sensitivity as s

        STATE_CATEGORIES.update({
            "sensible": tuple(s.CATEGORIES) + s.PERSONAL_CATEGORIES + s.BANK_CATEGORIES + s.RISKY_CATEGORIES,
            "mot-de-passe": s.PASSWORD_CATEGORIES,
            "cle-ou-jeton": s.KEY_CATEGORIES,
            "donnees-personnelles": s.PERSONAL_CATEGORIES,
            "bancaire": s.BANK_CATEGORIES,
            "fichiers-a-risque": s.RISKY_CATEGORIES,
        })
    return STATE_CATEGORIES


def _system(path: str) -> bool:
    """Recycle bin, restore points… (same list as the sensitivity counts): never tagged."""
    from app.services.sensitivity import in_system_folder

    return in_system_folder(path)


def path_hash(path: str) -> str:
    return hashlib.sha1(path.strip("\\").lower().encode("utf-8")).hexdigest()


def supported(query: str) -> bool:
    """True when every criterion of the condition can be judged on a sub-folder (and there is at least one)."""
    filters, words = folder_query.parse(query)
    if words.strip() or not filters:
        return False
    states = _categories()
    return all(item.key == "path" or (item.key == "is" and re.sub(r"\s+", "-", folder_query.fold(item.value)) in states) for item in filters)


def _base(root_path: str) -> str:
    """\\\\host\\share\\a\\b → a\\b (the governed folder inside its share)."""
    parts = [part for part in re.split(r"[\\/]+", str(root_path or "")) if part]
    return "\\".join(parts[2:])


def _words(name: str) -> set[str]:
    return {word for word in re.split(r"[^a-z0-9]+", folder_query.fold(name)) if word}


def _findings_by_folder(db: Session, root_id: int, base: str) -> dict[str, set[str]]:
    """{sub-folder path from the share: categories of the files found right in it} (files marked false positive left out)."""
    row = db.execute(text("SELECT findings_json, ignored_json FROM storage_root_sensitivity WHERE storage_root_id = :id"), {"id": int(root_id)}).first()
    if not row:
        return {}
    try:
        findings = json.loads(row[0] or "[]")
        ignored = {str(item.get("path", "")).lower() for item in json.loads(row[1] or "[]") if isinstance(item, dict)}
    except ValueError:
        return {}
    out: dict[str, set[str]] = {}
    for item in findings if isinstance(findings, list) else []:
        path = str((item or {}).get("path") or "").strip("\\")
        if not path or path.lower() in ignored:
            continue
        # Paths of the scan are from the governed folder or from the share: from the share here
        if base and not (path.lower() == base.lower() or path.lower().startswith(base.lower() + "\\")):
            path = f"{base}\\{path}"
        folder = path.rsplit("\\", 1)[0] if "\\" in path else ""
        out.setdefault(folder, set()).add(str(item.get("category") or ""))
    return out


def matching_folders(db: Session, row: dict[str, Any], query: str) -> list[str]:
    """The sub-folders of this governed folder that match the condition (never the governed folder itself)."""
    from app.services import modules

    root_id = int(row.get("storage_root_id") or 0)
    base = _base(str(row.get("root_path") or ""))
    filters, _words_left = folder_query.parse(query)
    states = _categories()
    found = _findings_by_folder(db, root_id, base) if any(item.key == "is" for item in filters) else {}
    candidates = {path.strip("\\") for path in found}
    if any(item.key == "path" for item in filters):
        candidates |= {path.strip("\\") for path in modules.folder_paths(root_id)}
    inside = [path for path in candidates if path and path.lower() != base.lower() and not _system(path)
              and (not base or path.lower().startswith(base.lower() + "\\"))]

    def test(path: str, item: folder_query.Filter) -> bool:
        if item.key == "path":
            wanted = [word for word in re.split(r"[^a-z0-9]+", folder_query.fold(item.value)) if word]
            return bool(wanted) and all(word in _words(path.rsplit("\\", 1)[-1]) for word in wanted)
        groups = states.get(re.sub(r"\s+", "-", folder_query.fold(item.value)), ())
        return bool(found.get(path, set()) & set(groups))

    return sorted(path for path in inside if all(test(path, item) != item.neg for item in filters))


def apply(db: Session, policy_id: int, tag_id: int, root_id: int, paths: list[str], *, remove: bool) -> tuple[int, int]:
    """The tag of the policy on these sub-folders; those it no longer matches lose it (remove). Returns (added, removed)."""
    wanted = {path_hash(path): path for path in paths}
    current = {str(h): int(i) for i, h in db.execute(
        text("SELECT id, path_hash FROM folder_tags WHERE storage_root_id = :root AND tag_id = :tag AND policy_id = :policy"),
        {"root": int(root_id), "tag": int(tag_id), "policy": int(policy_id)}).all()}
    new = [{"root": int(root_id), "path": wanted[h][:1024], "hash": h, "tag": int(tag_id), "policy": int(policy_id)} for h in wanted if h not in current]
    if new:
        db.execute(text("""INSERT IGNORE INTO folder_tags (storage_root_id, path, path_hash, tag_id, policy_id)
                           VALUES (:root, :path, :hash, :tag, :policy)"""), new)
    gone = [current[h] for h in current if h not in wanted]
    if remove and gone:
        db.execute(text("DELETE FROM folder_tags WHERE id IN :ids").bindparams(bindparam("ids", expanding=True)), {"ids": gone})
    return len(new), len(gone) if remove else 0


def for_root(db: Session, root_id: int) -> list[dict[str, Any]]:
    """[{path, tags: [{id, name, color}]}] of the sub-folders of a governed folder."""
    rows = db.execute(text("""SELECT ft.path, t.id, t.name, t.color FROM folder_tags ft JOIN tags t ON t.id = ft.tag_id AND t.deleted_at IS NULL
                              WHERE ft.storage_root_id = :root ORDER BY ft.path, t.name"""), {"root": int(root_id)}).all()
    out: dict[str, dict[str, Any]] = {}
    for path, tag_id, name, color in rows:
        out.setdefault(path.lower(), {"path": path, "tags": []})["tags"].append({"id": int(tag_id), "name": name, "color": color})
    return list(out.values())


def names_by_root(db: Session) -> dict[int, list[str]]:
    """{governed folder: names of the tags of its sub-folders}, for « tag:… » of the search and the policies."""
    try:
        rows = db.execute(text("""SELECT DISTINCT ft.storage_root_id, t.name FROM folder_tags ft
                                  JOIN tags t ON t.id = ft.tag_id AND t.deleted_at IS NULL""")).all()
    except Exception:  # table not created yet (pack 162)
        db.rollback()
        return {}
    out: dict[int, list[str]] = {}
    for root_id, name in rows:
        out.setdefault(int(root_id), []).append(str(name))
    return out
