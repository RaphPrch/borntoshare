"""
BornToShare – Wizard SQL Runner (GOLD)

- Deterministic execution order
- MariaDB / MySQL safe
- View dependency–friendly
- Transaction-safe per file
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Iterable, Optional

from app.db import get_connection

logger = logging.getLogger("wizard.sql")
logger.setLevel(logging.INFO)

SQL_DIR = Path(__file__).resolve().parent / "sql"

# -------------------------------------------------------------------
# SQL safety guards
# -------------------------------------------------------------------

FORBIDDEN_TABLES: set[str] = set()

# Detect real table usage keywords
SQL_TABLE_CONTEXT = r"\b(from|join|into|update|delete\s+from)\b"

# Explicit STUB detector
STUB_FROM_PATTERN = re.compile(
    r"from\s*\(\s*select\s+1\s*\)",
    re.IGNORECASE | re.MULTILINE,
)

# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def _iter_sql_files(kind: str) -> Iterable[Path]:
    files = sorted(p for p in SQL_DIR.glob("*.sql") if p.is_file())

    if kind == "schema":
        # schema + views + indexes (structure only)
        return [
            p for p in files
            if p.name.startswith(("01_", "02_", "03_", "04_", "06_"))
        ]

    if kind == "seed":
        return [p for p in files if p.name.startswith("05_")]

    return files



def _assert_sql_is_safe(sql: str, filename: str) -> None:
    """
    Guard against forbidden legacy tables.
    Views are allowed to JOIN real tables.
    """
    lowered = sql.lower()

    # Allow STUB views
    if STUB_FROM_PATTERN.search(lowered):
        return

    # Only block explicit forbidden tables
    for table in FORBIDDEN_TABLES:
        pattern = rf"{SQL_TABLE_CONTEXT}\s+{table}\b"
        if re.search(pattern, lowered):
            raise RuntimeError(
                f"[SQL GUARD] Forbidden table '{table}' used in {filename}"
            )


def _split_sql_statements(sql: str) -> list[str]:
    """
    Robust SQL splitter.
    Handles:
    - multiline CREATE VIEW
    - JSON expressions
    - comments
    """
    statements: list[str] = []
    buffer: list[str] = []
    in_string = False

    for line in sql.splitlines():
        stripped = line.strip()

        # Skip comments
        if stripped.startswith("--") or not stripped:
            continue

        # Track string literals (simple but enough for SQL)
        in_string ^= stripped.count("'") % 2 == 1

        buffer.append(line)

        if not in_string and stripped.endswith(";"):
            stmt = "\n".join(buffer).rstrip(";").strip()
            if stmt:
                statements.append(stmt)
            buffer.clear()

    if buffer:
        stmt = "\n".join(buffer).strip()
        if stmt:
            statements.append(stmt)

    return statements


def _run_sql_file(cursor, path: Path, conn) -> None:
    """
    Execute a SQL file atomically.
    """
    logger.info("[SQL] executing %s", path.name)
    sql = path.read_text(encoding="utf-8")

    _assert_sql_is_safe(sql, path.name)
    statements = _split_sql_statements(sql)

    try:
        for stmt in statements:
            cursor.execute(stmt)
        conn.commit()
    except Exception:
        conn.rollback()
        logger.exception("[SQL] failed in %s", path.name)
        raise


# -------------------------------------------------------------------
# Public API
# -------------------------------------------------------------------

def run_sql_pack(db_name: str, root_cfg: Optional[dict] = None) -> None:
    """Run schema + views + indexes + seed."""
    conn = get_connection(database=True, db_name=db_name, root_cfg=root_cfg)

    try:
        cur = conn.cursor()
        for p in _iter_sql_files("all"):
            _run_sql_file(cur, p, conn)
    finally:
        conn.close()


def run_schema_pack(db_name: str, root_cfg: Optional[dict] = None) -> None:
    """Run schema + views + indexes only."""
    conn = get_connection(database=True, db_name=db_name, root_cfg=root_cfg)

    try:
        cur = conn.cursor()
        for p in _iter_sql_files("schema"):
            _run_sql_file(cur, p, conn)
    finally:
        conn.close()


def run_seed_pack(db_name: str, root_cfg: Optional[dict] = None) -> None:
    """Run seed only."""
    conn = get_connection(database=True, db_name=db_name, root_cfg=root_cfg)

    try:
        cur = conn.cursor()
        for p in _iter_sql_files("seed"):
            _run_sql_file(cur, p, conn)
    finally:
        conn.close()


# -------------------------------------------------------------------
# Backward compatibility
# -------------------------------------------------------------------

def run_initial_schema(db_name: str, root_cfg: Optional[dict] = None) -> None:
    run_schema_pack(db_name=db_name, root_cfg=root_cfg)


def run_seed_sql(db_name: str, root_cfg: Optional[dict] = None) -> None:
    run_seed_pack(db_name=db_name, root_cfg=root_cfg)
