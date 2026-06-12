from __future__ import annotations

from pathlib import Path
from typing import Optional

from core.errors import SecretInvalidRefError

SM_PREFIX = "sm://"


def normalize_secret_relative_ref(relative_ref: str) -> str:
    raw = str(relative_ref or "").strip().replace("\\", "/")
    if not raw:
        raise SecretInvalidRefError(message="Empty secret reference", ref=relative_ref)

    if raw.startswith("/"):
        raise SecretInvalidRefError(message="Absolute secret path is forbidden", ref=relative_ref)

    raw_parts = raw.split("/")
    if any(part == ".." for part in raw_parts):
        raise SecretInvalidRefError(message="Path traversal detected", ref=relative_ref)

    parts = [part for part in raw_parts if part and part != "."]
    normalized = "/".join(parts)
    if not normalized:
        raise SecretInvalidRefError(message="Empty secret reference", ref=relative_ref)
    return normalized


def sm_ref_to_relative(secret_ref: str) -> str:
    ref = str(secret_ref or "").strip()
    if not ref.startswith(SM_PREFIX):
        raise SecretInvalidRefError(message="Secret ref must start with sm://", ref=secret_ref)
    return normalize_secret_relative_ref(ref[len(SM_PREFIX) :])


def build_sm_ref(name_or_ref: str) -> str:
    raw = str(name_or_ref or "").strip()
    rel = sm_ref_to_relative(raw) if raw.startswith(SM_PREFIX) else normalize_secret_relative_ref(raw)
    return f"{SM_PREFIX}{rel}"


def normalize_secret_path(base_dir: Path, relative_ref: str) -> Path:
    rel = normalize_secret_relative_ref(relative_ref)
    candidate = (base_dir / rel).resolve()
    base_resolved = base_dir.resolve()
    try:
        candidate.relative_to(base_resolved)
    except ValueError as exc:
        raise SecretInvalidRefError(message="Secret path escapes base directory", ref=relative_ref) from exc
    return candidate


def sm_ref_to_file_path(base_dir: Path, secret_ref: str) -> Path:
    rel = sm_ref_to_relative(secret_ref)
    return Path(f"{normalize_secret_path(base_dir, rel)}.enc")
