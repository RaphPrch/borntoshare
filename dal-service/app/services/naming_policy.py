from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


DEFAULT_REPLACE_MAP: dict[str, str] = {
    "\\\\": "_",
    "/": "_",
    " ": "_",
    "-": "_",
}

DEFAULT_GLOBAL_POLICY: dict[str, Any] = {
    "id": 1,
    "group_prefix": "B2S",
    "template": "{PREFIX}_{ROOTCODE}_{PERM}",
    "normalize_uppercase": True,
    "max_sam_length": 64,
    "replace_map_json": json.dumps(DEFAULT_REPLACE_MAP, separators=(",", ":")),
    "rootcode_strategy": "BASENAME",
}

ALLOWED_TEMPLATE_TOKENS = {"PREFIX", "ROOTCODE", "PERM"}


def _perm_token_equivalent(value: str) -> str:
    raw = str(value or "").strip().upper()
    if raw in {"READ", "R", "RX", "READ_ONLY", "READ-ONLY", "RO"}:
        return "RX"
    if raw in {
        "WRITE",
        "W",
        "RW",
        "MODIFY",
        "CHANGE",
        "CONTRIBUTION",
        "FULL",
        "FULL_CONTROL",
        "FULLCONTROL",
    }:
        return "RW"
    return raw


def _canonical_perm_token(value: str) -> str:
    normalized = _perm_token_equivalent(value)
    if normalized in {"RX", "RW"}:
        return normalized
    return str(value or "").strip().upper()


def _to_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    raw = str(value).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _normalize_replace_map(value: Any) -> dict[str, str]:
    if isinstance(value, dict):
        return {str(k): str(v) for k, v in value.items()}
    raw = str(value or "").strip()
    if not raw:
        return dict(DEFAULT_REPLACE_MAP)
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return {str(k): str(v) for k, v in parsed.items()}
    except Exception:
        pass
    return dict(DEFAULT_REPLACE_MAP)


def _collapse_underscores(value: str) -> str:
    return re.sub(r"_+", "_", value).strip("_")


def _dedupe_adjacent_segments(value: str) -> str:
    segments = [seg for seg in str(value or "").split("_") if seg]
    if not segments:
        return ""
    deduped: list[str] = [segments[0]]
    for seg in segments[1:]:
        if seg != deduped[-1]:
            deduped.append(seg)
    return "_".join(deduped)


def normalize_rootcode_strategy(value: Any) -> str:
    raw = str(value or "BASENAME").strip().upper()
    if raw in {"BASENAME", "PATH_ALL"}:
        return raw
    return "BASENAME"


def serialize_rootcode_strategy_for_storage(value: Any) -> str:
    return normalize_rootcode_strategy(value)


def validate_template_tokens(template: str) -> None:
    raw = str(template or "")
    tokens = set(re.findall(r"\{([A-Z_]+)\}", raw))
    unknown = sorted(token for token in tokens if token not in ALLOWED_TEMPLATE_TOKENS)
    if unknown:
        raise ValueError(
            "Template contains unsupported token(s): "
            + ", ".join(f"{{{t}}}" for t in unknown)
            + ". Allowed tokens: {PREFIX}, {ROOTCODE}, {PERM}."
        )


def sanitize_token(value: str, *, replace_map: dict[str, str], uppercase: bool) -> str:
    out = str(value or "")
    for src, dst in replace_map.items():
        out = out.replace(str(src), str(dst))
    out = re.sub(r"[^A-Za-z0-9_]", "_", out)
    out = _collapse_underscores(out)
    if uppercase:
        out = out.upper()
    return out


def split_storage_path_segments(storage_root_path: str) -> list[str]:
    normalized = str(storage_root_path or "").strip().replace("\\", "/")
    if not normalized:
        return []

    if normalized.startswith("//"):
        trimmed = normalized[2:]
        parts = [p for p in trimmed.split("/") if p]
        if len(parts) <= 1:
            return []
        return parts[1:]

    return [p for p in normalized.split("/") if p]


def compute_rootcode(
    storage_root_path: str,
    *,
    strategy: str,
    replace_map: dict[str, str],
    uppercase: bool,
) -> str:
    parts = split_storage_path_segments(storage_root_path)
    normalized_strategy = normalize_rootcode_strategy(strategy)
    # Rootcode maps to the folder basename by default.
    if normalized_strategy == "PATH_ALL":
        parts = parts
    else:
        parts = parts[-1:]

    cleaned = [
        sanitize_token(p, replace_map=replace_map, uppercase=uppercase)
        for p in parts
        if str(p or "").strip()
    ]
    cleaned = [c for c in cleaned if c]
    rootcode = _collapse_underscores("_".join(cleaned))
    return rootcode or "ROOT"


def enforce_sam_length(value: str, *, max_len: int, uppercase: bool) -> str:
    raw = str(value or "")
    if len(raw) <= max_len:
        return raw

    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:6]
    digest = digest.upper() if uppercase else digest.lower()

    if max_len <= 7:
        return raw[:max_len]
    return f"{raw[: max_len - 7]}_{digest}"


def resolve_group_name_from_effective_policy(
    *,
    effective_policy: dict[str, Any],
    zone_code: str,
    storage_root_path: str,
    perm: str,
    suffix: str | None = None,
    profile: str | None = None,
) -> dict[str, str]:
    replace_map = _normalize_replace_map(effective_policy.get("replace_map_json"))
    uppercase = _to_bool(effective_policy.get("normalize_uppercase"), True)
    strategy = normalize_rootcode_strategy(effective_policy.get("rootcode_strategy"))

    prefix = sanitize_token(
        str(effective_policy.get("group_prefix") or "B2S"),
        replace_map=replace_map,
        uppercase=uppercase,
    )
    rootcode = compute_rootcode(
        storage_root_path,
        strategy=strategy,
        replace_map=replace_map,
        uppercase=uppercase,
    )
    perm_token = sanitize_token(
        _canonical_perm_token(str(perm or "")),
        replace_map=replace_map,
        uppercase=uppercase,
    )
    suffix_token = sanitize_token(str(suffix or ""), replace_map=replace_map, uppercase=uppercase)
    profile_token = sanitize_token(str(profile or ""), replace_map=replace_map, uppercase=uppercase)

    perm_equivalent = _perm_token_equivalent(perm_token)
    suffix_equivalent = _perm_token_equivalent(suffix_token)
    profile_equivalent = _perm_token_equivalent(profile_token)

    template = str(effective_policy.get("template") or "{PREFIX}_{ROOTCODE}_{PERM}")
    validate_template_tokens(template)
    rendered = (
        template.replace("{PREFIX}", prefix)
        .replace("{ROOTCODE}", rootcode)
        .replace("{PERM}", perm_token)
    )

    if suffix_token and suffix_equivalent != perm_equivalent:
        rendered = f"{rendered}_{suffix_token}"
    if profile_token and profile_equivalent not in {perm_equivalent, suffix_equivalent}:
        rendered = f"{rendered}_{profile_token}"

    rendered = _collapse_underscores(sanitize_token(rendered, replace_map=replace_map, uppercase=uppercase))
    rendered = _dedupe_adjacent_segments(rendered)

    try:
        max_len = int(effective_policy.get("max_sam_length") or 64)
    except Exception:
        max_len = 64
    if max_len <= 0:
        max_len = 64

    sam = enforce_sam_length(rendered, max_len=max_len, uppercase=uppercase)
    return {"samAccountName": sam, "cn": sam}


def load_global_policy(db: Session) -> dict[str, Any]:
    row = db.execute(
        text(
            """
            SELECT id, group_prefix, template, normalize_uppercase, max_sam_length, replace_map_json, rootcode_strategy
            FROM naming_policy_global
            WHERE id = 1
            """
        )
    ).mappings().first()

    if not row:
        return dict(DEFAULT_GLOBAL_POLICY)

    out = dict(DEFAULT_GLOBAL_POLICY)
    out.update(dict(row))
    out["normalize_uppercase"] = _to_bool(out.get("normalize_uppercase"), True)
    out["rootcode_strategy"] = normalize_rootcode_strategy(out.get("rootcode_strategy"))
    try:
        out["max_sam_length"] = int(out.get("max_sam_length") or 64)
    except Exception:
        out["max_sam_length"] = 64
    return out


def load_zone_policy(db: Session, zone_id: int) -> dict[str, Any] | None:
    row = db.execute(
        text(
            """
            SELECT
              scope_id AS zone_id,
              override_enabled,
              group_prefix,
              template,
              normalize_uppercase,
              max_sam_length,
              replace_map_json,
              rootcode_strategy
            FROM naming_policy_overrides
            WHERE scope_type = 'zone'
              AND scope_id = :zone_id
            """
        ),
        {"zone_id": int(zone_id)},
    ).mappings().first()
    if not row:
        return None
    out = dict(row)
    out["override_enabled"] = _to_bool(out.get("override_enabled"), False)
    if out.get("normalize_uppercase") is not None:
        out["normalize_uppercase"] = _to_bool(out.get("normalize_uppercase"), True)
    if out.get("rootcode_strategy") is not None:
        out["rootcode_strategy"] = normalize_rootcode_strategy(out.get("rootcode_strategy"))
    return out


def _load_scope_override_policy(db: Session, *, scope_type: str, scope_id: int) -> dict[str, Any] | None:
    if scope_type not in {"zone", "storage_endpoint", "storage_root"}:
        return None
    row = db.execute(
        text(
            """
            SELECT
              scope_type,
              scope_id,
              override_enabled,
              group_prefix,
              template,
              normalize_uppercase,
              max_sam_length,
              replace_map_json,
              rootcode_strategy
            FROM naming_policy_overrides
            WHERE scope_type = :scope_type
              AND scope_id = :scope_id
            LIMIT 1
            """
        ),
        {
            "scope_type": str(scope_type),
            "scope_id": int(scope_id),
        },
    ).mappings().first()
    if not row:
        return None
    out = dict(row)
    out["override_enabled"] = _to_bool(out.get("override_enabled"), False)
    if out.get("normalize_uppercase") is not None:
        out["normalize_uppercase"] = _to_bool(out.get("normalize_uppercase"), True)
    if out.get("rootcode_strategy") is not None:
        out["rootcode_strategy"] = normalize_rootcode_strategy(out.get("rootcode_strategy"))
    return out


def _apply_override_policy(base_policy: dict[str, Any], override_policy: dict[str, Any] | None) -> dict[str, Any]:
    if not override_policy or not _to_bool(override_policy.get("override_enabled"), False):
        return base_policy
    effective = dict(base_policy)
    for key in (
        "group_prefix",
        "template",
        "normalize_uppercase",
        "max_sam_length",
        "replace_map_json",
        "rootcode_strategy",
    ):
        if override_policy.get(key) is not None:
            effective[key] = override_policy.get(key)
    return effective


def resolve_effective_policy(
    db: Session,
    zone_id: int | None,
    storage_endpoint_id: int | None = None,
    storage_root_id: int | None = None,
) -> dict[str, Any]:
    global_policy = load_global_policy(db)
    effective = dict(global_policy)

    if zone_id is not None:
        zone_policy = load_zone_policy(db, int(zone_id))
        effective = _apply_override_policy(effective, zone_policy)

    if storage_endpoint_id is not None:
        endpoint_policy = _load_scope_override_policy(
            db,
            scope_type="storage_endpoint",
            scope_id=int(storage_endpoint_id),
        )
        effective = _apply_override_policy(effective, endpoint_policy)

    if storage_root_id is not None:
        root_policy = _load_scope_override_policy(
            db,
            scope_type="storage_root",
            scope_id=int(storage_root_id),
        )
        effective = _apply_override_policy(effective, root_policy)

    return effective


def resolve_zone_context(db: Session, zone_ref: Any) -> tuple[int | None, str]:
    if zone_ref is None:
        return None, ""

    raw = str(zone_ref).strip()
    if not raw:
        return None, ""

    if raw.isdigit():
        row = db.execute(
            text("SELECT id, code FROM zones WHERE id = :zone_id"),
            {"zone_id": int(raw)},
        ).mappings().first()
        if row:
            return int(row["id"]), str(row.get("code") or "")
        return int(raw), ""

    row = db.execute(
        text("SELECT id, code FROM zones WHERE UPPER(code) = UPPER(:code) LIMIT 1"),
        {"code": raw},
    ).mappings().first()
    if row:
        return int(row["id"]), str(row.get("code") or raw)
    return None, raw


def resolve_group_name(
    db: Session,
    *,
    zone_ref: Any,
    storage_root_path: str,
    perm: str,
    suffix: str | None = None,
    profile: str | None = None,
) -> dict[str, str]:
    zone_id, zone_code = resolve_zone_context(db, zone_ref)
    effective = resolve_effective_policy(db, zone_id)
    return resolve_group_name_from_effective_policy(
        effective_policy=effective,
        zone_code=zone_code,
        storage_root_path=storage_root_path,
        perm=perm,
        suffix=suffix,
        profile=profile,
    )
