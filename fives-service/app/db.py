"""The two databases of the module, created by the installation wizard (make wizard):
- b2s_fives: what the module computes over time (history of the measures, its settings);
- b2s_fives_inventory: the fingerprints of the files (duplicates between folders), the one that grows.
Their tables come from SQL packs applied by the migration account; the module only reads and writes."""
from __future__ import annotations

import logging
from urllib.parse import quote_plus

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import settings

logger = logging.getLogger("fives.db")


def _url(database: str) -> str:
    return (f"mysql+pymysql://{quote_plus(settings.FIVES_DB_USER)}:{quote_plus(settings.FIVES_DB_PASSWORD)}"
            f"@{settings.FIVES_DB_HOST}:{settings.FIVES_DB_PORT}/{database}?charset=utf8mb4")


engine = create_engine(_url(settings.FIVES_DB_NAME), pool_pre_ping=True, pool_recycle=1800)
inventory_engine = create_engine(_url(settings.FIVES_INVENTORY_DB_NAME), pool_pre_ping=True, pool_recycle=1800)
SessionLocal = sessionmaker(bind=engine, autoflush=False)
InventorySession = sessionmaker(bind=inventory_engine, autoflush=False)

# Created by the migration account (wizard-ui/backend/app/sql/fives*, applied by the wizard and make deploy):
# the account of the module only reads and writes
TABLES = {"fives": ["content_history", "module_settings", "scan_runs", "scan_chunks", "scan_state"], "inventory": ["fingerprints"]}


def check_schema() -> None:
    """Raises when a table of the module is missing (databases not installed, or a pack not applied)."""
    for target, names in ((engine, TABLES["fives"]), (inventory_engine, TABLES["inventory"])):
        with target.connect() as connection:
            for name in names:
                connection.execute(text(f"SELECT 1 FROM `{name}` LIMIT 0"))
    logger.info("Module schema ready")
