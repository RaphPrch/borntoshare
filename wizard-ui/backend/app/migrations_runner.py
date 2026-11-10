"""The SQL packs of backend/app/sql, applied in order: schema/ → views/ → indexes/ for the database of BornToShare,
logging/schema → logging/indexes for its audit database. Every file is idempotent (scripts/deploy.sh replays them)."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

from .db import get_connection

logger = logging.getLogger("wizard.sql")

SQL_DIR = Path(__file__).resolve().parent / "sql"

# Files that others depend on: first, then the rest by name
_SCHEMA_FIRST = ["020_identity.sql", "080_snapshots.sql"]
_VIEWS_FIRST = ["010_views_base.sql", "011_views_context.sql", "011b_views_effective_access.sql", "012_views_dashboard.sql"]


def _files(directory: Path, first: list[str] | None = None) -> list[Path]:
    paths = sorted(p for p in directory.glob("*.sql") if p.is_file()) if directory.exists() else []
    order = {name: index for index, name in enumerate(first or [])}
    return sorted(paths, key=lambda p: (0, order[p.name]) if p.name in order else (1, p.name))


def split_statements(sql: str) -> list[str]:
    """Statements of a pack, on « ; » at the end of a line (the packs have no procedure nor trigger)."""
    statements: list[str] = []
    buffer: list[str] = []
    for line in sql.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        buffer.append(line)
        if stripped.endswith(";"):
            statement = "\n".join(buffer).rstrip().rstrip(";").strip()
            if statement:
                statements.append(statement)
            buffer = []
    if buffer and "\n".join(buffer).strip():
        statements.append("\n".join(buffer).strip())
    return statements


def _run(db_name: str, paths: Iterable[Path], root_cfg: dict) -> int:
    conn = get_connection(root_cfg=root_cfg, database=True, db_name=db_name)
    cur = conn.cursor()
    count = 0
    try:
        for path in paths:
            logger.info("[SQL] %s", path.relative_to(SQL_DIR))
            for statement in split_statements(path.read_text(encoding="utf-8")):
                cur.execute(statement)
                # mysql-connector: every result set must be read before the next statement
                if getattr(cur, "with_rows", False):
                    cur.fetchall()
                while cur.nextset():
                    if getattr(cur, "with_rows", False):
                        cur.fetchall()
            count += 1
        conn.commit()
        return count
    except Exception:
        conn.rollback()
        logger.exception("[SQL] pack failed")
        raise
    finally:
        cur.close()
        conn.close()


def run_schema_pack(db_name: str, root_cfg: dict) -> int:
    """Tables, views and indexes of the database of BornToShare; the number of files applied."""
    paths = _files(SQL_DIR / "schema", _SCHEMA_FIRST) + _files(SQL_DIR / "views", _VIEWS_FIRST) + _files(SQL_DIR / "indexes")
    return _run(db_name, paths, root_cfg)


def run_logging_schema_pack(db_name: str, root_cfg: dict) -> int:
    """Tables and indexes of the audit database."""
    return _run(db_name, _files(SQL_DIR / "logging" / "schema") + _files(SQL_DIR / "logging" / "indexes"), root_cfg)


def run_fives_packs(db_name: str, inventory_db_name: str, root_cfg: dict) -> int:
    """Tables of the 5S module: sql/fives on its database, sql/fives_inventory on its inventory."""
    return _run(db_name, _files(SQL_DIR / "fives"), root_cfg) + _run(inventory_db_name, _files(SQL_DIR / "fives_inventory"), root_cfg)
