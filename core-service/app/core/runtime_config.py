"""Database connection chosen in Advanced Settings › Infrastructure.

The connection cannot be stored in the database it describes: it lives in a JSON file of the runtime
directory (B2S_RUNTIME_DIR, mounted read-write) and replaces the DB_* variables at the next start of
core-service. Without the file, the .env values are used.

File content:
  {"mode": "fields", "host": ..., "port": 3306, "name": ..., "user": ..., "password": ...,
   "logging_name": ..., "updated_at": ..., "updated_by": ...}
  {"mode": "dsn", "dsn": "mariadb+pymysql://user:pwd@host:3306/b2s", "logging_dsn": ..., ...}
The file holds the password, like .env: it is written with 0600 rights and never sent back to the UI.
"""
from __future__ import annotations

import json
import os
import urllib.parse
from pathlib import Path
from typing import Any

DATABASE_FILE = "database.json"


def runtime_dir() -> Path:
    return Path(os.getenv("B2S_RUNTIME_DIR", "/etc/b2s/runtime"))


def database_file() -> Path:
    return runtime_dir() / DATABASE_FILE


def read_database_config() -> dict[str, Any] | None:
    path = database_file()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("mode") in {"fields", "dsn"} else None


def write_database_config(config: dict[str, Any]) -> None:
    """Atomic write, owner-only rights."""
    directory = runtime_dir()
    directory.mkdir(parents=True, exist_ok=True)
    tmp = directory / f".{DATABASE_FILE}.tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2)
    os.replace(tmp, database_file())


def runtime_dir_writable() -> bool:
    directory = runtime_dir()
    return directory.is_dir() and os.access(directory, os.W_OK)


def parse_dsn(dsn: str) -> dict[str, Any]:
    """Host, port, database and user of a DSN (for display and checks)."""
    parsed = urllib.parse.urlsplit(str(dsn or "").strip())
    if not parsed.scheme or not parsed.hostname:
        raise ValueError("The connection string must look like mariadb+pymysql://user:password@host:3306/database")
    return {
        "driver": parsed.scheme,
        "host": parsed.hostname,
        "port": parsed.port or 3306,
        "name": parsed.path.lstrip("/") or None,
        "user": urllib.parse.unquote(parsed.username or "") or None,
        "has_password": bool(parsed.password),
    }


def build_url(*, driver: str, host: str, port: int, name: str, user: str, password: str) -> str:
    return (
        f"{driver}://{urllib.parse.quote_plus(user)}:{urllib.parse.quote_plus(password)}"
        f"@{host}:{int(port)}/{name}"
    )
