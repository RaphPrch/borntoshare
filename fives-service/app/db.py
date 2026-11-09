"""The two databases of the module, created by the installation (scripts/modules/fives/install.sh):
- b2s_fives: what the module computes over time (history of the measures, its settings);
- b2s_fives_inventory: the fingerprints of the files (duplicates between folders), the one that grows.
The module creates its own tables at startup (idempotent) with its own account."""
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

SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS content_history (
      id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
      storage_root_id BIGINT NOT NULL,
      measured_at DATETIME NOT NULL,
      bytes BIGINT UNSIGNED NOT NULL,
      files INT UNSIGNED NULL,
      folders INT UNSIGNED NULL,
      cold_1y_bytes BIGINT UNSIGNED NULL,
      cold_3y_bytes BIGINT UNSIGNED NULL,
      junk_bytes BIGINT UNSIGNED NULL,
      duplicate_bytes BIGINT UNSIGNED NULL,
      UNIQUE KEY ux_content_history_root_hour (storage_root_id, measured_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS module_settings (
      setting_key VARCHAR(64) NOT NULL PRIMARY KEY,
      value_json LONGTEXT NULL,
      updated_by VARCHAR(190) NULL,
      updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
]

INVENTORY_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS fingerprints (
      id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
      storage_root_id BIGINT NOT NULL,
      fingerprint CHAR(64) NOT NULL,
      size_bytes BIGINT UNSIGNED NOT NULL,
      path VARCHAR(1024) NOT NULL,
      modified_at DATETIME NULL,
      KEY ix_fingerprints_print (fingerprint, size_bytes),
      KEY ix_fingerprints_root (storage_root_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
]


def create_schema() -> None:
    for target, statements in ((engine, SCHEMA), (inventory_engine, INVENTORY_SCHEMA)):
        with target.begin() as connection:
            for statement in statements:
                connection.execute(text(statement))
    logger.info("Module schema ready")
