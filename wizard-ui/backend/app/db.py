from __future__ import annotations

import os
import logging
from typing import Optional

import mysql.connector
from mysql.connector import Error

logger = logging.getLogger("wizard.db")
logger.setLevel(logging.INFO)

# ============================================================
# 🔧 DB CONNECTION
# ============================================================

def get_connection(
    database: bool = False,
    db_name: Optional[str] = None,
    root_cfg: Optional[dict] = None,
):
    """
    Crée une connexion MySQL pour le Wizard UI.

    - root_cfg : configuration fournie par le wizard (step DB)
    - sinon : variables d'environnement
    """

    if root_cfg:
        cfg = {
            "host": root_cfg.get("host", "localhost"),
            "port": int(root_cfg.get("port", 3306)),
            "user": root_cfg.get("user", "root"),
            "password": root_cfg.get("password", ""),
        }
        database_name = root_cfg.get("database")
    else:
        cfg = {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": int(os.getenv("DB_PORT", "3306")),
            "user": os.getenv("DB_USER", "root"),
            "password": os.getenv("DB_PASSWORD", ""),
        }
        database_name = os.getenv("DB_NAME")

    if database:
        cfg["database"] = db_name or database_name

    # 🔐 Ne jamais logguer le mot de passe
    safe_cfg = cfg.copy()
    if "password" in safe_cfg:
        safe_cfg["password"] = "***"

    logger.debug("[DB-CONNECT] Attempting → %s", safe_cfg)

    return mysql.connector.connect(**cfg)


# ============================================================
# 🧪 DB TEST
# ============================================================

def test_connection(root_cfg: dict) -> bool:
    """
    Teste la connexion MySQL avec une configuration fournie par le wizard.
    Ne sélectionne PAS de base (test root).
    """
    try:
        safe_cfg = root_cfg.copy()
        if "password" in safe_cfg:
            safe_cfg["password"] = "***"

        logger.debug("[DB-TEST] Testing connection with config: %s", safe_cfg)

        conn = get_connection(database=False, root_cfg=root_cfg)
        conn.close()

        logger.info("[DB-TEST] SUCCESS → DB connection OK")
        return True

    except Error as e:
        logger.error("[DB-TEST] FAILED → MySQL error: %s", e)
        return False

    except Exception as e:
        logger.exception("[DB-TEST] FAILED → Unexpected error")
        return False
