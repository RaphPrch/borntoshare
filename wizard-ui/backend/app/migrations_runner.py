"""
BornToShare – Wizard SQL Runner (GOLD)

Runs the SQL pack located in: backend/app/sql/
- 01_schema.sql
- 02_views.sql
- 03_indexes.sql
- 04_seed.sql

Compatible with MySQL / MariaDB.
No PostgreSQL-specific features (no multi=True).

This runner enforces:
- strict execution order
- MySQL-compatible statement splitting
- protection against legacy / forbidden SQL references
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Iterable, Optional

from .db import get_connection

logger = logging.getLogger("wizard.sql")
logger.setLevel(logging.INFO)

SQL_DIR = Path(__file__).resolve().parent / "sql"

# -------------------------------------------------------------------
# SQL safety guards
# -------------------------------------------------------------------

# Forbidden legacy tables / features (schema v1)
# Intentionally empty for now – kept as a guardrail for future migrations
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
def _iter_sql_files(kind: str) -> Iterable[Path]:
    """
    Return SQL files ordered by filename prefix.

    kind:
      - "schema" -> 01_schema.sql, 02_views.sql, 03_indexes.sql
      - "seed"   -> 04_seed.sql
      - "all"    -> everything in folder
    """
    files = sorted(p for p in SQL_DIR.glob("*.sql") if p.is_file())

    if kind == "seed":
        return [p for p in files if p.name.startswith("04_")]

    if kind == "schema":
        return [p for p in files if p.name.startswith(("01_", "02_", "03_"))]

    return files


def _assert_sql_is_safe(sql: str, filename: str) -> None:
    """
    Fail fast if legacy or forbidden SQL TABLE references are detected.

    Rules:
    - real tables are forbidden (FROM / JOIN / INSERT INTO / UPDATE / DELETE FROM)
    - STUB views (FROM (SELECT 1) ...) are explicitly allowed
    """
    lowered = sql.lower()

    # ------------------------------------------------------------
    # Allow explicit STUB views
    # ------------------------------------------------------------
    if STUB_FROM_PATTERN.search(lowered):
        logger.debug("[SQL GUARD] stub view detected in %s", filename)
        return

    # ------------------------------------------------------------
    # Block forbidden real tables
    # ------------------------------------------------------------
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
    sql = path.read_text(encoding="utf-8")

    _assert_sql_is_safe(sql, path.name)

    statements = _split_sql_statements(sql)

    for stmt in statements:
        cursor.execute(stmt)


# -------------------------------------------------------------------
# Public API
# -------------------------------------------------------------------
def run_sql_pack(db_name: str, root_cfg: Optional[dict] = None) -> None:
    """Run schema + views + indexes + seed."""
    conn = get_connection(database=True, db_name=db_name, root_cfg=root_cfg)
    cur = conn.cursor()

    try:
        for p in _iter_sql_files("all"):
            logger.info("[SQL] running %s", p.name)
            _run_sql_file(cur, p)
        conn.commit()
    except Exception:
        conn.rollback()
        logger.exception("[SQL] SQL pack execution failed")
        raise
    finally:
        cur.close()
        conn.close()


def run_schema_pack(db_name: str, root_cfg: Optional[dict] = None) -> None:
    """Run schema + views + indexes only."""
    conn = get_connection(database=True, db_name=db_name, root_cfg=root_cfg)
    cur = conn.cursor()

    try:
        for p in _iter_sql_files("schema"):
            logger.info("[SQL] running %s", p.name)
            _run_sql_file(cur, p)
        conn.commit()
    except Exception:
        conn.rollback()
        logger.exception("[SQL] Schema pack execution failed")
        raise
    finally:
        cur.close()
        conn.close()


def run_seed_pack(db_name: str, root_cfg: Optional[dict] = None) -> None:
    """Run seed only."""
    conn = get_connection(database=True, db_name=db_name, root_cfg=root_cfg)
    cur = conn.cursor()

    try:
        for p in _iter_sql_files("seed"):
            logger.info("[SQL] running %s", p.name)
            _run_sql_file(cur, p)
        conn.commit()
    except Exception:
        conn.rollback()
        logger.exception("[SQL] Seed pack execution failed")
        raise
    finally:
        cur.close()
        conn.close()


# -------------------------------------------------------------------
# Backward-compat aliases (used by routes/import_wizard.py)
# -------------------------------------------------------------------
def run_initial_schema(db_name: str, root_cfg: Optional[dict] = None) -> None:
    run_schema_pack(db_name=db_name, root_cfg=root_cfg)


def run_seed_sql(db_name: str, root_cfg: Optional[dict] = None) -> None:
    run_seed_pack(db_name=db_name, root_cfg=root_cfg)
