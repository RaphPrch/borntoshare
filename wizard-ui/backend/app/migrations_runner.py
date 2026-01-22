"""
BornToShare – Wizard SQL Runner (GOLD)

Runs the SQL packs located in: backend/app/sql/

Structure:
- sql/schema/*.sql     -> core tables, constraints
- sql/views/*.sql      -> read models (views)
- sql/indexes/*.sql    -> indexes
- sql/seeds/*.sql      -> DEV-only reference seeds (optional)

Compatible with MySQL / MariaDB.
No PostgreSQL-specific features.

This runner enforces:
- strict execution order
- MySQL-compatible statement splitting
- separation of schema / views / indexes / seed
- protection against forbidden legacy SQL
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Iterable, Optional

from .db import get_connection

logger = logging.getLogger("wizard.sql")
logger.setLevel(logging.INFO)

SQL_DIR = Path(__file__).resolve().parent / "sql"

SCHEMA_DIR = SQL_DIR / "schema"
VIEWS_DIR = SQL_DIR / "views"
INDEXES_DIR = SQL_DIR / "indexes"
SEEDS_DIR = SQL_DIR / "seeds"

# Optional private seeds dir (not committed)
# - Relative paths are resolved from SQL_DIR
_PRIVATE_SEEDS_DIR_RAW = os.getenv("WIZARD_PRIVATE_SEEDS_DIR", "").strip()


def _get_private_seeds_dir() -> Optional[Path]:
    if not _PRIVATE_SEEDS_DIR_RAW:
        return None

    p = Path(_PRIVATE_SEEDS_DIR_RAW)
    if not p.is_absolute():
        p = (SQL_DIR / p).resolve()

    return p if p.exists() else None

# -------------------------------------------------------------------
# SQL safety guards
# -------------------------------------------------------------------

# Reserved for future legacy protection (v1 tables, etc.)
FORBIDDEN_TABLES: set[str] = set()

# SQL keywords that imply REAL table usage
SQL_TABLE_CONTEXT = r"(from|join|into|update|delete\s+from)"

# Explicit STUB detector: FROM (SELECT 1 ...)
STUB_FROM_PATTERN = re.compile(
    r"from\s*\(\s*select\s+1\s*\)",
    re.IGNORECASE | re.MULTILINE,
)

# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------
def _iter_sql_files(directory: Path) -> Iterable[Path]:
    """
    Return SQL files ordered by filename.
    """
    if not directory.exists():
        return []
    return sorted(p for p in directory.glob("*.sql") if p.is_file())


def _assert_sql_is_safe(sql: str, filename: str) -> None:
    """
    Fail fast if legacy or forbidden SQL TABLE references are detected.

    Rules:
    - real legacy tables are forbidden (FROM / JOIN / INSERT INTO / UPDATE / DELETE FROM)
    - STUB views (FROM (SELECT 1) ...) are explicitly allowed
    """
    lowered = sql.lower()

    # Allow explicit STUB views
    if STUB_FROM_PATTERN.search(lowered):
        logger.debug("[SQL GUARD] stub view detected in %s", filename)
        return

    for table in FORBIDDEN_TABLES:
        pattern = rf"\b{SQL_TABLE_CONTEXT}\s+{re.escape(table)}\b"
        if re.search(pattern, lowered):
            raise RuntimeError(
                f"[SQL GUARD] Forbidden legacy table '{table}' detected in {filename}"
            )


def _split_sql_statements(sql: str) -> list[str]:
    """
    Split SQL statements safely on ';'.

    Assumptions (valid for our SQL packs):
    - no stored procedures
    - no triggers
    - no BEGIN/END blocks
    """
    statements: list[str] = []
    buffer: list[str] = []

    for line in sql.splitlines():
        stripped = line.strip()

        # Skip empty lines and comments
        if not stripped or stripped.startswith("--"):
            continue

        buffer.append(line)

        if stripped.endswith(";"):
            stmt = "\n".join(buffer).rstrip(";").strip()
            if stmt:
                statements.append(stmt)
            buffer = []

    if buffer:
        stmt = "\n".join(buffer).strip()
        if stmt:
            statements.append(stmt)

    return statements


def _run_sql_file(cursor, path: Path) -> None:
    """
    Execute a SQL file containing multiple statements.

    MySQL / MariaDB compatible.
    """
    logger.info("[SQL] running %s", path.relative_to(SQL_DIR))
    sql = path.read_text(encoding="utf-8")

    _assert_sql_is_safe(sql, path.name)

    for stmt in _split_sql_statements(sql):
        cursor.execute(stmt)


def _run_pack(
    db_name: str,
    paths: Iterable[Path],
    root_cfg: Optional[dict] = None,
) -> None:
    conn = get_connection(database=True, db_name=db_name, root_cfg=root_cfg)
    cur = conn.cursor()

    try:
        for p in paths:
            _run_sql_file(cur, p)
        conn.commit()
    except Exception:
        conn.rollback()
        logger.exception("[SQL] SQL pack execution failed")
        raise
    finally:
        cur.close()
        conn.close()


# -------------------------------------------------------------------
# Public API
# -------------------------------------------------------------------
def run_schema_pack(db_name: str, root_cfg: Optional[dict] = None) -> None:
    """
    Run schema + views + indexes.
    """
    paths = (
        list(_iter_sql_files(SCHEMA_DIR))
        + list(_iter_sql_files(VIEWS_DIR))
        + list(_iter_sql_files(INDEXES_DIR))
    )
    _run_pack(db_name=db_name, paths=paths, root_cfg=root_cfg)


def run_seed_pack(db_name: str, root_cfg: Optional[dict] = None) -> None:
    """
    Run DEV-only seed pack.
    """
    paths = list(_iter_sql_files(SEEDS_DIR))

    private_dir = _get_private_seeds_dir()
    if private_dir:
        logger.info("[SQL] Including private seeds from %s", private_dir)
        paths += list(_iter_sql_files(private_dir))

    if not paths:
        logger.info("[SQL] No seed files found, skipping")
        return

    _run_pack(db_name=db_name, paths=paths, root_cfg=root_cfg)



def run_sql_pack(db_name: str, root_cfg: Optional[dict] = None) -> None:
    """
    Run full SQL pack (schema + views + indexes + seed).
    """
    paths = (
        list(_iter_sql_files(SCHEMA_DIR))
        + list(_iter_sql_files(VIEWS_DIR))
        + list(_iter_sql_files(INDEXES_DIR))
        + list(_iter_sql_files(SEEDS_DIR))
    )
    _run_pack(db_name=db_name, paths=paths, root_cfg=root_cfg)


# -------------------------------------------------------------------
# Backward-compat aliases (used by routes/import_wizard.py)
# -------------------------------------------------------------------
def run_initial_schema(db_name: str, root_cfg: Optional[dict] = None) -> None:
    run_schema_pack(db_name=db_name, root_cfg=root_cfg)


def run_seed_sql(db_name: str, root_cfg: Optional[dict] = None) -> None:
    run_seed_pack(db_name=db_name, root_cfg=root_cfg)
