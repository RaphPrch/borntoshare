"""The express search of the folders, on the server side: the condition of the smart policies.

Same language as the search field of the Folders page (frontend lib/components/storage-roots/folder-query.ts):
free text plus « key:value » filters, « - » to exclude, quotes for a value with spaces.
  tag: gardien: zone: serveur: dfs: partage: alerte: taille> taille<
  est: alerte injoignable sain sans-gardien sans-tag heritage-rompu demandes a-revalider vide non-mesure
       non-teste dfs sensible non-analyse mot-de-passe cle-ou-jeton correction quota sans-quota quota-plein quota-demande
       donnees-froides encombre
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable

ALIASES = {
    "tag": "tag", "tags": "tag", "etiquette": "tag",
    "gardien": "guardian", "guardian": "guardian", "g": "guardian",
    "zone": "zone", "z": "zone",
    "serveur": "server", "server": "server", "filer": "server",
    "dfs": "dfs", "namespace": "dfs",
    "partage": "share", "share": "share",
    "est": "is", "is": "is", "etat": "is",
    "alerte": "alert", "alert": "alert",
    "taille": "size", "size": "size",
}
_TOKEN = re.compile(r'(-?)([a-zA-Zéèêà]+)([:<>])("[^"]*"?|\S*)')


def fold(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value if value is not None else ""))
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn").lower().strip()


@dataclass(frozen=True)
class Filter:
    key: str
    op: str
    value: str
    neg: bool
    raw: str


def parse(query: str) -> tuple[list[Filter], str]:
    filters: list[Filter] = []
    words: list[str] = []
    source = str(query or "")
    index = 0
    while index < len(source):
        if source[index].isspace():
            index += 1
            continue
        match = _TOKEN.match(source, index)
        key = ALIASES.get(fold(match.group(2))) if match else None
        if match and key and match.group(4) != "":
            filters.append(Filter(key, match.group(3), match.group(4).strip('"'), match.group(1) == "-", match.group(0)))
            index = match.end()
            continue
        end = index
        while end < len(source) and not source[end].isspace():
            end += 1
        if not (match and key and match.group(4) == ""):
            words.append(source[index:end])
        index = max(end, index + 1)
    return filters, " ".join(words)


_UNITS = {"o": 1, "b": 1, "ko": 1024, "kb": 1024, "mo": 1024**2, "mb": 1024**2, "go": 1024**3, "gb": 1024**3, "to": 1024**4, "tb": 1024**4}


def bytes_of(value: str) -> float | None:
    match = re.match(r"^(\d+(?:\.\d+)?)\s*([a-z]*)$", fold(value).replace(",", "."))
    if not match:
        return None
    unit = _UNITS.get(match.group(2) or "o")
    return float(match.group(1)) * unit if unit else None


def tag_names(row: dict) -> list[str]:
    tags = row.get("tags") if isinstance(row.get("tags"), list) else []
    return [str(tag.get("label") or tag.get("name") or tag.get("code") or "") for tag in tags if isinstance(tag, dict)]


def _parts(row: dict) -> list[str]:
    return [part for part in re.split(r"[\\/]+", str(row.get("root_path") or "")) if part]


def _alert_types(row: dict) -> list[str]:
    return [part for part in str(row.get("open_alert_types") or "").split(",") if part]


def _size(row: dict) -> float | None:
    value = row.get("content_size_bytes", row.get("estimated_size_bytes"))
    return None if value in (None, "") else float(value)


STATES: dict[str, Callable[[dict], bool]] = {
    "alerte": lambda row: int(row.get("open_alerts_count") or 0) > 0,
    "injoignable": lambda row: "unreachable" in str(row.get("effective_availability") or "") or row.get("last_probe_status") == "failed",
    "sain": lambda row: int(row.get("open_alerts_count") or 0) == 0 and row.get("last_probe_status") == "success",
    "sans-gardien": lambda row: int(row.get("guardians_count") or 0) == 0,
    "sans-tag": lambda row: not tag_names(row),
    "heritage-rompu": lambda row: row.get("inheritance_broken") is True,
    "demandes": lambda row: int(row.get("pending_validation_count") or 0) > 0,
    "a-revalider": lambda row: row.get("needs_revalidation") is True,
    "vide": lambda row: _size(row) == 0,
    "non-mesure": lambda row: _size(row) is None,
    "non-teste": lambda row: not row.get("last_probe_at"),
    "dfs": lambda row: bool(row.get("dfs_path")),
    "sensible": lambda row: int(row.get("sensitive_files") or 0) > 0,
    "non-analyse": lambda row: row.get("sensitive_files") is None,
    "mot-de-passe": lambda row: int(row.get("password_files") or 0) > 0,
    "cle-ou-jeton": lambda row: int(row.get("key_files") or 0) > 0,
    "correction": lambda row: row.get("remediation_status") in {"open", "overdue"},
    # More than half of the data untouched for a year · clutter files (caches, lock files, temporary, copies)
    "donnees-froides": lambda row: bool(row.get("cold_1y_bytes")) and float(row["cold_1y_bytes"]) > 0.5 * float(_size(row) or 0) > 0,
    "encombre": lambda row: int(row.get("junk_files") or 0) > 0,
    "quota": lambda row: row.get("quota_limit_bytes") is not None,
    "sans-quota": lambda row: row.get("quota_limit_bytes") is None,
    "quota-plein": lambda row: row.get("quota_used_percent") is not None and float(row["quota_used_percent"]) >= float(row.get("quota_warn_percent") or 85),
    "quota-demande": lambda row: int(row.get("quota_pending_requests") or 0) > 0,
}


def _test(row: dict, item: Filter) -> bool:
    wanted = fold(item.value)

    def has(values: list[Any]) -> bool:
        return any(wanted in fold(value) for value in values)

    if item.key == "tag":
        return has(tag_names(row))
    if item.key == "guardian":
        return has(list(row.get("guardian_names") or []))
    if item.key == "zone":
        return has([row.get("zone_name")])
    if item.key == "server":
        return has([row.get("storage_endpoint_name"), row.get("storage_endpoint_host"), (_parts(row) or [""])[0]])
    if item.key == "dfs":
        return has([row.get("dfs_path")])
    if item.key == "share":
        parts = _parts(row)
        return has([parts[1] if len(parts) > 1 else ""])
    if item.key == "alert":
        return has(_alert_types(row))
    if item.key == "is":
        state = STATES.get(re.sub(r"\s+", "-", wanted))
        return bool(state and state(row))
    if item.key == "size":
        limit, value = bytes_of(item.value), _size(row)
        if limit is None or value is None:
            return False
        return value < limit if item.op == "<" else value > limit if item.op == ">" else value == limit
    return True


def _text_match(row: dict, text: str) -> bool:
    needle = fold(text)
    if not needle:
        return True
    haystack = fold(" ".join(str(v or "") for v in (row.get("storage_root_name"), row.get("root_path"), row.get("dfs_path"),
                                                    row.get("storage_endpoint_name"), row.get("zone_name"), *tag_names(row))))
    return needle in haystack


def matches(row: dict, query: str) -> bool:
    filters, text = parse(query)
    return all(_test(row, item) != item.neg for item in filters) and _text_match(row, text)


def unknown_states(query: str) -> list[str]:
    """« est:… » values the language does not know (a typo would match nothing, silently)."""
    filters, _text = parse(query)
    return [item.value for item in filters if item.key == "is" and re.sub(r"\s+", "-", fold(item.value)) not in STATES]
