import mysql.connector
from mysql.connector import Error
from typing import Optional
import logging

logger = logging.getLogger("wizard.db")
logger.setLevel(logging.DEBUG)

def get_connection(database: bool = False, db_name: Optional[str] = None, root_cfg: Optional[dict] = None):
    """Crée une connexion MySQL pour le wizard UI."""
    if root_cfg:
        cfg = {
            "host": root_cfg.get("host", "localhost"),
            "port": int(root_cfg.get("port", 3306)),
            "user": root_cfg.get("user", "root"),
            "password": root_cfg.get("password", ""),
        }
    else:
        import os
        cfg = {
            "host": os.getenv("DB_HOST", "localhost"),
            "port": int(os.getenv("DB_PORT", "3306")),
            "user": os.getenv("DB_USER", "root"),
            "password": os.getenv("DB_PASSWORD", ""),
        }

    if database:
        cfg["database"] = db_name or (root_cfg.get("database") if root_cfg else os.getenv("DB_NAME"))

    logger.debug(f"[DB-CONNECT] Attempting → {cfg}")

    return mysql.connector.connect(**cfg)


def test_connection(root_cfg: dict) -> bool:
    try:
        logger.debug(f"[DB-TEST] Testing connection with config: {root_cfg}")
        conn = get_connection(database=False, root_cfg=root_cfg)
        conn.close()
        logger.info("[DB-TEST] SUCCESS → DB connection OK")
        return True

    except Error as e:
        logger.error(f"[DB-TEST] FAILED → MySQL error: {e}")
        return False

    except Exception as e:
        logger.error(f"[DB-TEST] FAILED → Unexpected error: {e}")
        return False
