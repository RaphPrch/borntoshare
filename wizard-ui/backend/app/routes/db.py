from __future__ import annotations

import socket
import time
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..db import get_connection

logger = logging.getLogger("wizard.db")

router = APIRouter(
    prefix="/db",
    tags=["wizard-db"],
)

# ============================================================
# 📦 PAYLOADS
# ============================================================

class DbNetworkPayload(BaseModel):
    host: str = Field(..., description="Database host or IP")
    port: int = Field(3306, description="Database port")


class DbAuthPayload(DbNetworkPayload):
    user: str = Field(..., description="Database user")
    password: str = Field(..., description="Database password")
    database: Optional[str] = Field(
        None,
        description="Optional database name",
    )


class DbPrecheckPayload(DbAuthPayload):
    db_name: str = Field(..., description="Target database name to check")
    app_sql_user: str = Field(..., description="App SQL user to check")

# ============================================================
# 🌐 DNS / TCP / LATENCY DIAGNOSTIC
# ============================================================

@router.post("/diagnostic")
def network_diagnostic(payload: DbNetworkPayload):
    logger.debug(
        "DB diagnostic start",
        extra={"host": payload.host, "port": payload.port},
    )

    result = {
        "dns_ok": False,
        "tcp_ok": False,
        "latency_ms": None,
    }

    try:
        start = time.time()

        # DNS
        ip = socket.gethostbyname(payload.host)
        logger.debug("DNS resolution OK", extra={"host": payload.host, "ip": ip})
        result["dns_ok"] = True

        # TCP
        sock = socket.create_connection((ip, payload.port), timeout=3)
        sock.close()
        logger.debug("TCP connectivity OK", extra={"ip": ip, "port": payload.port})
        result["tcp_ok"] = True

        result["latency_ms"] = int((time.time() - start) * 1000)

    except Exception as e:
        logger.warning(
            "Network diagnostic failed",
            extra={"host": payload.host, "port": payload.port},
            exc_info=e,
        )

    return result

# ============================================================
# 🔌 BASIC DB CONNECTION TEST
# ============================================================

@router.post("/test")
def test_db(payload: DbAuthPayload):
    logger.debug(
        "DB connection test start",
        extra={
            "host": payload.host,
            "port": payload.port,
            "user": payload.user,
        },
    )

    try:
        conn = get_connection(
            database=False,
            root_cfg={
                "host": payload.host,
                "port": payload.port,
                "user": payload.user,
                "password": payload.password,
            },
        )
        conn.close()

        logger.info(
            "DB connection OK",
            extra={"user": payload.user, "host": payload.host},
        )

    except Exception as e:
        logger.error(
            "DB connection failed",
            extra={
                "host": payload.host,
                "port": payload.port,
                "user": payload.user,
            },
            exc_info=e,
        )
        raise HTTPException(
            status_code=400,
            detail="Unable to connect to database (invalid host, port or credentials)",
        )

    return {"status": "ok"}

# ============================================================
# 🔐 SQL PRIVILEGES TEST (SAFE + ROBUST)
# ============================================================

@router.post("/privileges-test")
def privileges_test(payload: DbAuthPayload):
    logger.debug(
        "SQL privileges test start",
        extra={
            "host": payload.host,
            "port": payload.port,
            "user": payload.user,
        },
    )

    privileges = {
        "create_database": False,
        "create_user": False,
        "grant": False,
        "create_table": False,
    }

    conn = None
    cur = None

    try:
        conn = get_connection(
            database=False,
            root_cfg={
                "host": payload.host,
                "port": payload.port,
                "user": payload.user,
                "password": payload.password,
            },
        )
        cur = conn.cursor()

        # ----------------------------------------------------
        # SHOW DATABASES (returns rows → MUST fetch)
        # ----------------------------------------------------
        try:
            cur.execute("SHOW DATABASES")
            cur.fetchall()  # 🔑 CRITICAL (mysql-connector)
            privileges["create_database"] = True
            logger.debug("Privilege OK: SHOW DATABASES")
        except Exception as e:
            logger.warning("Privilege FAILED: SHOW DATABASES", exc_info=e)

        # ----------------------------------------------------
        # SHOW GRANTS (returns rows → MUST fetch)
        # ----------------------------------------------------
        try:
            cur.execute("SHOW GRANTS FOR CURRENT_USER")
            cur.fetchall()  # 🔑 CRITICAL
            privileges["grant"] = True
            logger.debug("Privilege OK: SHOW GRANTS")
        except Exception as e:
            logger.warning("Privilege FAILED: SHOW GRANTS", exc_info=e)

        # ----------------------------------------------------
        # REALISTIC CREATE DATABASE + TABLE TEST
        # ----------------------------------------------------
        try:
            cur.execute("CREATE DATABASE IF NOT EXISTS __b2s_priv_test_db")
            cur.execute(
                "CREATE TABLE __b2s_priv_test_db.__b2s_priv_test (id INT)"
            )
            cur.execute("DROP DATABASE __b2s_priv_test_db")
            privileges["create_table"] = True
            logger.debug("Privilege OK: CREATE DATABASE + TABLE")
        except Exception as e:
            logger.warning(
                "Privilege FAILED: CREATE DATABASE/TABLE",
                exc_info=e,
            )

        # CREATE USER is inferred from GRANT capability
        privileges["create_user"] = privileges["grant"]

    except Exception as e:
        logger.error(
            "SQL privilege test fatal error",
            extra={
                "host": payload.host,
                "user": payload.user,
            },
            exc_info=e,
        )
        raise HTTPException(
            status_code=400,
            detail="Unable to verify SQL privileges",
        )

    finally:
        try:
            if cur:
                cur.close()
            if conn:
                conn.close()
        except Exception:
            pass

    logger.info(
        "SQL privilege test completed",
        extra={
            "user": payload.user,
            "privileges": privileges,
        },
    )

    return {
        "status": "ok",
        "privileges": privileges,
        "all_required_ok": privileges["create_table"],
        "is_root": payload.user.lower() == "root",
    }


# ============================================================
# 🔎 PRECHECK (DB exists / user exists)
# ============================================================


@router.post("/precheck")
def precheck(payload: DbPrecheckPayload):
    """
    Vérifications légères, avant l'import final:
    - La base `db_name` existe-t-elle ?
    - L'utilisateur SQL applicatif existe-t-il déjà ?

    Utilise les credentials fournis (généralement root DB) pour interroger.
    """

    db_exists = None
    app_user_exists = None

    conn = None
    cur = None
    try:
        conn = get_connection(
            database=False,
            root_cfg={
                "host": payload.host,
                "port": payload.port,
                "user": payload.user,
                "password": payload.password,
            },
        )
        cur = conn.cursor()

        # DB exists?
        try:
            cur.execute(
                "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s LIMIT 1",
                (payload.db_name,),
            )
            db_exists = cur.fetchone() is not None
        except Exception as e:
            logger.warning("Precheck DB exists failed", exc_info=e)

        # User exists?
        try:
            # Works for MySQL/MariaDB with sufficient privileges
            cur.execute(
                "SELECT 1 FROM mysql.user WHERE user = %s LIMIT 1",
                (payload.app_sql_user,),
            )
            app_user_exists = cur.fetchone() is not None
        except Exception as e:
            logger.warning("Precheck user exists failed", exc_info=e)

    finally:
        try:
            if cur:
                cur.close()
            if conn:
                conn.close()
        except Exception:
            pass

    return {
        "status": "ok",
        "db_exists": db_exists,
        "app_user_exists": app_user_exists,
    }
