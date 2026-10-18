from __future__ import annotations

import os
import logging
from typing import Optional

import mysql.connector

logger = logging.getLogger("wizard.db")
logger.setLevel(logging.INFO)

# ============================================================
# 🔧 DB CONNECTION
# ============================================================

def get_connection(
    database: bool = False,
    db_name: Optional[str] = None,
    root_cfg: Optional[dict] = None,
    log_connection: bool = True,
):
    """
    Crée une connexion MySQL / MariaDB pour le Wizard UI.

    - root_cfg : configuration fournie par le wizard (step DB)
    - sinon     : variables d'environnement
    - database  : si True, sélectionne la base
    """

    if root_cfg:
        cfg = {
            "host": root_cfg.get("host"),
            "port": int(root_cfg.get("port", 3306)),
            "user": root_cfg.get("user"),
            "password": root_cfg.get("password"),
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

    # ⚠️ OPTIONS CRITIQUES (MariaDB distant / root / Podman)
    cfg.update({
        "connection_timeout": 5,
        "use_pure": True,
        "ssl_disabled": True,
        "auth_plugin": "mysql_native_password",
    })

    # 🔐 Ne jamais logguer le mot de passe
    safe_cfg = cfg.copy()
    if "password" in safe_cfg:
        safe_cfg["password"] = "***"

    if log_connection:
        logger.info("[DB-CONNECT] %s", safe_cfg)

    return mysql.connector.connect(**cfg)


# ============================================================
# 🧪 DB TEST
# ============================================================
