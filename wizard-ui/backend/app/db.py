"""Connections of the wizard to MariaDB: always with the account typed on screen (never written anywhere)."""
from __future__ import annotations

import logging
from typing import Optional

import mysql.connector

logger = logging.getLogger("wizard.db")


def get_connection(*, root_cfg: dict, database: bool = False, db_name: Optional[str] = None):
    """A connection with the account of root_cfg (host, port, user, password); on db_name when database is True."""
    cfg = {
        "host": root_cfg["host"],
        "port": int(root_cfg.get("port") or 3306),
        "user": root_cfg["user"],
        "password": root_cfg["password"],
        # MariaDB of the installation: no TLS on the data network, native password accounts
        "connection_timeout": 5,
        "use_pure": True,
        "ssl_disabled": True,
        "auth_plugin": "mysql_native_password",
    }
    if database:
        cfg["database"] = db_name
    logger.info("[DB-CONNECT] %s@%s:%s/%s", cfg["user"], cfg["host"], cfg["port"], cfg.get("database") or "")
    return mysql.connector.connect(**cfg)
