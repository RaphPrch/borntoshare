"""Connections of the wizard to MariaDB: always with the account typed on screen (never written anywhere)."""
from __future__ import annotations

import logging
import os
from typing import Optional

import mysql.connector

logger = logging.getLogger("wizard.db")
# The private authority of the MariaDB servers: /etc/b2s/certs in the container, capsule-runner/certs without it
DB_TLS_CA = os.getenv("DB_TLS_CA") or "/etc/b2s/certs/db-ca.pem"


def get_connection(*, root_cfg: dict, database: bool = False, db_name: Optional[str] = None):
    """A connection with the account of root_cfg (host, port, user, password); on db_name when database is True."""
    cfg = {
        "host": root_cfg["host"],
        "port": int(root_cfg.get("port") or 3306),
        "user": root_cfg["user"],
        "password": root_cfg["password"],
        "connection_timeout": 5,
        "use_pure": True,
        "auth_plugin": "mysql_native_password",
    }
    if root_cfg.get("tls"):
        # TLS (DB_TLS=on): encrypted, certificate and name of the server checked; the private authority when its file
        # is there (capsule-runner/certs/db-ca.pem), else the authorities of the system
        cfg.update(ssl_disabled=False, ssl_verify_cert=True, ssl_verify_identity=True)
        if os.path.isfile(DB_TLS_CA):
            cfg["ssl_ca"] = DB_TLS_CA
    else:
        cfg["ssl_disabled"] = True
    if database:
        cfg["database"] = db_name
    logger.info("[DB-CONNECT] %s@%s:%s/%s%s", cfg["user"], cfg["host"], cfg["port"], cfg.get("database") or "", " (TLS)" if root_cfg.get("tls") else "")
    return mysql.connector.connect(**cfg)
