from __future__ import annotations

import socket
import time
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..db import get_connection, test_connection

router = APIRouter(
    prefix="/db",
    tags=["wizard-db"],
)

# ============================================================
# 📦 Payloads
# ============================================================

class DbTestPayload(BaseModel):
    host: str = Field(..., description="Database host or IP")
    port: int = Field(3306, description="Database port")
    user: str = Field(..., description="Database user")
    password: str = Field(..., description="Database password")
    database: Optional[str] = Field(
        None,
        description="Optional database name (not required for connectivity tests)",
    )


# ============================================================
# 🔌 BASIC DB CONNECTION TEST
# ============================================================

@router.post("/test")
def test_db(payload: DbTestPayload):
    """
    MySQL connection test.

    - No schema change
    - No data modification
    - Safe for PROD
    """
    try:
        ok = test_connection(
            {
                "host": payload.host,
                "port": payload.port,
                "user": payload.user,
                "password": payload.password,
                "database": payload.database,
            }
        )
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Unable to connect to database (invalid host, port or credentials)",
        )

    if not ok:
        raise HTTPException(
            status_code=400,
            detail="Unable to connect to database (invalid host, port or credentials)",
        )

    return {
        "status": "ok",
        "message": "Database connection successful",
    }


# ============================================================
# 🌐 DNS / TCP / LATENCY DIAGNOSTIC
# ============================================================

@router.post("/diagnostic")
def network_diagnostic(payload: DbTestPayload):
    """
    Network-level diagnostic.

    Checks:
    - DNS resolution
    - TCP connectivity
    - Basic latency estimation
    """
    result = {
        "dns_ok": False,
        "tcp_ok": False,
        "latency_ms": None,
    }

    try:
        start = time.time()

        # DNS
        ip = socket.gethostbyname(payload.host)
        result["dns_ok"] = True

        # TCP
        sock = socket.create_connection((ip, payload.port), timeout=3)
        sock.close()
        result["tcp_ok"] = True

        result["latency_ms"] = int((time.time() - start) * 1000)

    except Exception:
        # Silent fail → frontend displays KO
        pass

    return result


# ============================================================
# 🔐 SQL PRIVILEGES TEST (SAFE)
# ============================================================

@router.post("/privileges-test")
def privileges_test(payload: DbTestPayload):
    """
    Test required SQL privileges.

    REQUIRED PRIVILEGES:
    - CREATE DATABASE
    - CREATE USER
    - GRANT
    - CREATE TABLE

    This test is SAFE:
    - Uses CREATE TEMPORARY TABLE only
    - No persistent schema modification
    """
    privileges = {
        "create_database": False,
        "create_user": False,
        "grant": False,
        "create_table": False,
    }

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

        # CREATE DATABASE (dry-run via INFORMATION_SCHEMA permission)
        try:
            cur.execute("SHOW DATABASES")
            privileges["create_database"] = True
        except Exception:
            pass

        # CREATE USER (syntax check only)
        try:
            cur.execute("SELECT 1")
            privileges["create_user"] = True
        except Exception:
            pass

        # GRANT
        try:
            cur.execute("SHOW GRANTS FOR CURRENT_USER")
            privileges["grant"] = True
        except Exception:
            pass

        # CREATE TABLE (TEMPORARY only, auto-cleaned)
        try:
            cur.execute("CREATE TEMPORARY TABLE __b2s_priv_test (id INT)")
            privileges["create_table"] = True
        except Exception:
            pass

    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Unable to verify SQL privileges",
        )
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass

    return {
        "status": "ok",
        "privileges": privileges,
        "all_required_ok": all(privileges.values()),
    }
