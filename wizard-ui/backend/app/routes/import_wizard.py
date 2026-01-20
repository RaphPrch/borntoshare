from fastapi import APIRouter, HTTPException
from mysql.connector import Error
import os
import re
import logging

from ..db import get_connection
from ..migrations_runner import run_initial_schema, run_seed_sql
from ..security import get_password_hash, validate_password_complexity

# ------------------------------------------------------------
# Router
# ------------------------------------------------------------
router = APIRouter(prefix="/import", tags=["import"])

WIZARD_MODE = os.getenv("WIZARD_MODE", "dev").lower()

logger = logging.getLogger("wizard.import")
logger.setLevel(logging.INFO)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _validate_sql_identifier(value: str, label: str):
    if not value:
        raise HTTPException(status_code=400, detail=f"{label} requis.")
    if value.lower() == "root":
        raise HTTPException(status_code=400, detail=f"{label} invalide.")
    if not re.match(r"^[a-zA-Z0-9_]+$", value):
        raise HTTPException(
            status_code=400,
            detail=f"{label} invalide (caractères autorisés : a-zA-Z0-9_).",
        )


def _parse_bool(value, default=False) -> bool:
    """
    Robust bool parsing for wizard payloads.
    Accepts: true/false, "true"/"false", 1/0
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    if isinstance(value, int):
        return value == 1
    return default


# ----------------------------------------------------------------------
# Import principal
# ----------------------------------------------------------------------
@router.post("/")
async def import_config(payload: dict):
    """
    Import final du wizard.

    DEV:
      - création DB
      - comptes SQL
      - schema + views + indexes
      - seed AUTO
      - admin local

    PROD:
      - aucune action destructive
    """

    # ------------------------------------------------------------------
    # Payload
    # ------------------------------------------------------------------
    db_name = payload.get("db_name")
    root_cfg = payload.get("db_root")
    admin = payload.get("admin") or {}
    services = payload.get("services") or []

    app_sql_user = payload.get("app_sql_user") or "app_user"
    app_sql_password = payload.get("app_user_password") or "change_me_app"

    apply_seed_flag = _parse_bool(payload.get("apply_seed"), default=False)

    if not db_name or not root_cfg:
        raise HTTPException(status_code=400, detail="db_name et db_root sont requis.")

    _validate_sql_identifier(db_name, "Nom de base")
    _validate_sql_identifier(app_sql_user, "Compte SQL applicatif")

    logger.info(
        "[WIZARD] mode=%s apply_seed_flag=%s",
        WIZARD_MODE,
        apply_seed_flag,
    )

    # ------------------------------------------------------------------
    # MODE PROD (SAFE EXIT)
    # ------------------------------------------------------------------
    if WIZARD_MODE == "prod":
        logger.warning("[WIZARD] PROD mode – import skipped")
        return {
            "ok": True,
            "message": "Mode PROD : aucune modification directe.",
        }

    # ==================================================================
    # 1. Création de la base
    # ==================================================================
    conn = get_connection(database=False, root_cfg=root_cfg)
    cur = conn.cursor()
    try:
        cur.execute(
            f"""
            CREATE DATABASE IF NOT EXISTS `{db_name}`
            CHARACTER SET utf8mb4
            COLLATE utf8mb4_unicode_ci
            """
        )
        conn.commit()
    except Error as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur création base : {e}")
    finally:
        cur.close()
        conn.close()

    # ==================================================================
    # 2. Création des comptes SQL
    # ==================================================================
    conn = get_connection(database=False, root_cfg=root_cfg)
    cur = conn.cursor()
    try:
        cur.execute(
            f"CREATE USER IF NOT EXISTS `{app_sql_user}`@'%' IDENTIFIED BY %s",
            (app_sql_password,),
        )
        cur.execute(
            f"GRANT ALL PRIVILEGES ON `{db_name}`.* TO `{app_sql_user}`@'%'"
        )

        for svc in services:
            db_user = svc.get("db_user")
            db_password = svc.get("db_password")

            if not db_user or not db_password:
                continue

            _validate_sql_identifier(db_user, "Compte SQL service")

            cur.execute(
                f"CREATE USER IF NOT EXISTS `{db_user}`@'%' IDENTIFIED BY %s",
                (db_password,),
            )
            cur.execute(
                f"GRANT ALL PRIVILEGES ON `{db_name}`.* TO `{db_user}`@'%'"
            )

        cur.execute("FLUSH PRIVILEGES")
        conn.commit()

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur comptes SQL : {e}")
    finally:
        cur.close()
        conn.close()

    # ==================================================================
    # 3. Schéma / vues / indexes
    # ==================================================================
    logger.info("[WIZARD] Running schema pack")
    run_initial_schema(db_name=db_name, root_cfg=root_cfg)

    # 🔥 CORRECTION CLÉ 🔥
    # En DEV → seed toujours appliqué
    if WIZARD_MODE == "dev" or apply_seed_flag:
        logger.info("[WIZARD] Running seed pack")
        run_seed_sql(db_name=db_name, root_cfg=root_cfg)
    else:
        logger.info("[WIZARD] Seed skipped")

    # ==================================================================
    # 4. Création admin local
    # ==================================================================
    app_conn = get_connection(database=True, db_name=db_name, root_cfg=root_cfg)
    app_cur = app_conn.cursor()

    try:
        username = admin.get("username") or "admin"
        email = admin.get("email") or "admin@local"
        raw_password = admin.get("password")

        if not raw_password:
            raise HTTPException(status_code=400, detail="Mot de passe admin requis.")

        validate_password_complexity(raw_password)
        password_hash = get_password_hash(raw_password)

        # Nettoyage idempotent
        app_cur.execute(
            """
            DELETE FROM local_credential
            WHERE identity_id IN (
                SELECT id FROM identity
                WHERE auth_source = 'local'
                  AND (username = %s OR email = %s)
            )
            """,
            (username, email),
        )

        app_cur.execute(
            """
            DELETE FROM identity
            WHERE auth_source = 'local'
              AND (username = %s OR email = %s)
            """,
            (username, email),
        )

        # Création identité
        app_cur.execute(
            """
            INSERT INTO identity (
                username,
                email,
                display_name,
                auth_source,
                is_active
            )
            VALUES (%s, %s, %s, 'local', 1)
            """,
            (username, email, username),
        )

        identity_id = app_cur.lastrowid

        # Création credentials
        app_cur.execute(
            """
            INSERT INTO local_credential (
                identity_id,
                password_hash,
                password_version
            )
            VALUES (%s, %s, 'b2s$v=1$bcrypt')
            """,
            (identity_id, password_hash),
        )

        app_conn.commit()

    except HTTPException:
        app_conn.rollback()
        raise
    except Exception as e:
        app_conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erreur création admin : {e}")
    finally:
        app_cur.close()
        app_conn.close()

    return {
        "ok": True,
        "message": "Import terminé : base, schéma, seed et admin local créés.",
    }
