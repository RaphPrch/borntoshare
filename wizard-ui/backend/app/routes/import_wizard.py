from __future__ import annotations

import os
import re
import logging
from typing import Dict, Any

from fastapi import APIRouter, HTTPException
from mysql.connector import Error

from ..db import get_connection
from ..migrations_runner import (
    run_initial_schema,
    run_seed_sql,
    run_logging_schema_pack,
    run_logging_seed_pack,
)
from ..security import validate_password_complexity
from ..settings import settings
from ..admin_logic import create_local_admin_if_needed

# ------------------------------------------------------------
# Router
# ------------------------------------------------------------
router = APIRouter(prefix="/import", tags=["import"])

logger = logging.getLogger("wizard.import")

# Configure logger
logging.basicConfig(level=logging.DEBUG)  # Log level set to DEBUG for visibility

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _is_prod() -> bool:
    return settings.is_prod()


def _validate_sql_identifier(value: str, label: str) -> None:
    if not value:
        logger.error(f"{label} requis.")  # Log error here
        raise HTTPException(status_code=400, detail=f"{label} requis.")
    if value.lower() == "root":
        logger.error(f"{label} invalide.")  # Log error here
        raise HTTPException(status_code=400, detail=f"{label} invalide.")
    if not re.match(r"^[a-zA-Z0-9_]+$", value):
        logger.error(f"{label} invalide (caractères autorisés : a-zA-Z0-9_).")  # Log error here
        raise HTTPException(
            status_code=400,
            detail=f"{label} invalide (caractères autorisés : a-zA-Z0-9_).",
        )


def _parse_bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    if isinstance(value, int):
        return value == 1
    return default


def _validate_root_cfg(cfg: Dict[str, Any]) -> None:
    required = {"host", "port", "user", "password"}
    if not isinstance(cfg, dict):
        logger.error("db_root invalide.")  # Log error here
        raise HTTPException(status_code=400, detail="db_root invalide.")
    missing = required - set(cfg.keys())
    if missing:
        logger.error(f"db_root incomplet (manque: {', '.join(missing)})")  # Log error here
        raise HTTPException(
            status_code=400,
            detail=f"db_root incomplet (manque: {', '.join(missing)})",
        )


def _resolve_logging_root_cfg(logging_db: Dict[str, Any], default_root: Dict[str, Any]) -> Dict[str, Any]:
    host = str(logging_db.get("host") or default_root.get("host") or "").strip()
    port = int(logging_db.get("port") or default_root.get("port") or 3306)
    user = str(logging_db.get("user") or default_root.get("user") or "").strip()
    password = str(logging_db.get("password") or default_root.get("password") or "")

    if not host or not user:
        raise HTTPException(
            status_code=400,
            detail="logging_db host/user requis (ou hérité de db_root)"
        )

    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
    }


# ----------------------------------------------------------------------
# Import principal
# ----------------------------------------------------------------------
@router.post("/")
@router.post("/import")  # Ajout d'une route sans le slash final pour éviter les redirections
async def import_config(payload: dict):
    """
    Import final du wizard.

    DEV:
      - création DB
      - comptes SQL
      - schéma + vues + indexes
      - seed DEV optionnel
      - admin local

    PROD:
      - BLOQUÉ par défaut
      - AUTORISÉ uniquement si force_import=true
      - seed STRICTEMENT interdit
    """

    logger.info("========== WIZARD IMPORT START ==========")

    # ------------------------------------------------------------------
    # Payload extraction
    # ------------------------------------------------------------------
    db_name = payload.get("db_name")
    root_cfg = payload.get("db_root")
    admin = payload.get("admin") or {}
    services = payload.get("services") or []

    app_sql_user = payload.get("app_sql_user") or "b2s_app"
    app_sql_password = payload.get("app_user_password")
    logging_db = payload.get("logging_db") or {}

    apply_seed_flag = _parse_bool(payload.get("apply_seed"), default=False)
    force_import = _parse_bool(payload.get("force_import"), default=False)

    # ------------------------------------------------------------------
    # Basic validation
    # ------------------------------------------------------------------
    if not db_name or not root_cfg:
        logger.error("db_name et db_root sont requis.")  # Log error here
        raise HTTPException(status_code=400, detail="db_name et db_root sont requis.")

    if not app_sql_password:
        logger.error("Mot de passe du compte SQL applicatif requis.")  # Log error here
        raise HTTPException(
            status_code=400,
            detail="Mot de passe du compte SQL applicatif requis.",
        )

    _validate_root_cfg(root_cfg)
    _validate_sql_identifier(db_name, "Nom de base")
    _validate_sql_identifier(app_sql_user, "Compte SQL applicatif")

    if logging_db:
        if not isinstance(logging_db, dict):
            raise HTTPException(status_code=400, detail="logging_db invalide")

        required = {"db_name", "app_sql_user", "app_user_password"}
        missing = [k for k in required if not logging_db.get(k)]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"logging_db incomplet (manque: {', '.join(missing)})",
            )

        _validate_sql_identifier(str(logging_db.get("db_name")), "Nom de base logging")
        _validate_sql_identifier(str(logging_db.get("app_sql_user")), "Compte SQL logging")
        validate_password_complexity(str(logging_db.get("app_user_password") or ""))

    logger.info(
        "[WIZARD] mode=%s | apply_seed=%s | force_import=%s",
        settings.MODE,
        apply_seed_flag,
        force_import,
    )

    # ------------------------------------------------------------------
    # MODE PROD — garde-fous
    # ------------------------------------------------------------------
    if _is_prod() and apply_seed_flag:
        logger.error("Seed interdit en environnement PROD.")  # Log error here
        raise HTTPException(
            status_code=400,
            detail="Seed interdit en environnement PROD.",
        )

    # ==================================================================
    # 1. Création de la base
    # ==================================================================
    logger.info("[WIZARD] Creating database '%s'", db_name)

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
        logger.info("[WIZARD] Database created / exists")
    except Error as e:
        conn.rollback()
        logger.exception("[WIZARD] Database creation failed")  # Log exception here
        raise HTTPException(status_code=500, detail=f"Erreur création base : {e}")
    finally:
        cur.close()
        conn.close()

    # Vérification que la base a bien été créée
    # NOTE: `get_connection(database=...)` attend un bool.
    # On doit passer `database=True` + `db_name=...`.
    conn = get_connection(database=True, db_name=db_name, root_cfg=root_cfg)
    try:
        cur = conn.cursor()
        cur.execute("SELECT DATABASE()")
        current_db = cur.fetchone()
        if current_db[0] != db_name:
            logger.error("La base de données n'a pas été créée correctement.")  # Log error here
            raise HTTPException(status_code=500, detail="La base de données n'a pas été créée correctement.")
        logger.info(f"[WIZARD] Vérification : Base {db_name} est active.")
    except Error as e:
        logger.exception(f"Erreur lors de la vérification de la base : {e}")  # Log exception here
        raise HTTPException(status_code=500, detail=f"Erreur lors de la vérification de la base : {e}")
    finally:
        cur.close()
        conn.close()

    # ==================================================================
    # 2. Création des comptes SQL
    # ==================================================================
    logger.info("[WIZARD] Creating SQL users")

    conn = get_connection(database=False, root_cfg=root_cfg)
    cur = conn.cursor()
    try:
        # Compte applicatif principal
        cur.execute(
            f"CREATE USER IF NOT EXISTS `{app_sql_user}`@'%' IDENTIFIED BY %s",
            (app_sql_password, ),
        )
        cur.execute(
            f"GRANT ALL PRIVILEGES ON `{db_name}`.* TO `{app_sql_user}`@'%'"
        )

        # Comptes SQL optionnels par service
        for svc in services:
            db_user = svc.get("db_user")
            db_password = svc.get("db_password")

            if not db_user or not db_password:
                continue

            _validate_sql_identifier(db_user, "Compte SQL service")

            cur.execute(
                f"CREATE USER IF NOT EXISTS `{db_user}`@'%' IDENTIFIED BY %s",
                (db_password, ),
            )
            cur.execute(
                f"GRANT ALL PRIVILEGES ON `{db_name}`.* TO `{db_user}`@'%'"
            )

        cur.execute("FLUSH PRIVILEGES")

        if logging_db:
            logging_db_name = str(logging_db.get("db_name"))
            logging_sql_user = str(logging_db.get("app_sql_user"))
            logging_sql_password = str(logging_db.get("app_user_password"))

            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{logging_db_name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )

            cur.execute(
                f"CREATE USER IF NOT EXISTS `{logging_sql_user}`@'%' IDENTIFIED BY %s",
                (logging_sql_password, )
            )
            cur.execute(
                f"GRANT ALL PRIVILEGES ON `{logging_db_name}`.* TO `{logging_sql_user}`@'%'"
            )

        conn.commit()
        logger.info("[WIZARD] SQL users ready")

    except Exception as e:
        conn.rollback()
        logger.exception("[WIZARD] SQL user creation failed")  # Log exception here
        raise HTTPException(status_code=500, detail=f"Erreur comptes SQL : {e}")
    finally:
        cur.close()
        conn.close()

    # ==================================================================
    # 3. Schéma / seed
    # ==================================================================
    logger.info("[WIZARD] Running schema pack")
    run_initial_schema(db_name=db_name, root_cfg=root_cfg)

    if logging_db:
        logging_root_cfg = _resolve_logging_root_cfg(logging_db, root_cfg)
        logging_db_name = str(logging_db.get("db_name"))
        os.environ["WIZARD_LOG_DB_ENABLED"] = "true"
        os.environ["WIZARD_LOG_DB_HOST"] = str(logging_root_cfg.get("host"))
        os.environ["WIZARD_LOG_DB_PORT"] = str(logging_root_cfg.get("port"))
        os.environ["WIZARD_LOG_DB_USER"] = str(logging_db.get("app_sql_user"))
        os.environ["WIZARD_LOG_DB_PASSWORD"] = str(logging_db.get("app_user_password"))
        os.environ["WIZARD_LOG_DB_NAME"] = logging_db_name

        logging_app_cfg = {
            "host": logging_root_cfg.get("host"),
            "port": logging_root_cfg.get("port"),
            "user": logging_db.get("app_sql_user"),
            "password": logging_db.get("app_user_password"),
        }

        logger.info("[WIZARD] Running dedicated logging SQL pack")
        run_logging_schema_pack(db_name=logging_db_name, root_cfg=logging_app_cfg)

        if apply_seed_flag:
            logger.info("[WIZARD] Running dedicated logging seed pack")
            run_logging_seed_pack(db_name=logging_db_name, root_cfg=logging_app_cfg)

    if apply_seed_flag:
        logger.info("[WIZARD] Running DEV seed pack")
        run_seed_sql(db_name=db_name, root_cfg=root_cfg)
    else:
        logger.info("[WIZARD] Seed skipped")

    # ==================================================================
    # 4. Admin local
    # ==================================================================
    username = admin.get("username") or "admin"
    email = admin.get("email") or "admin@local"
    raw_password = admin.get("password")

    if not raw_password:
        logger.error("Mot de passe admin requis.")  # Log error here
        raise HTTPException(status_code=400, detail="Mot de passe admin requis.")

    validate_password_complexity(raw_password)

    logger.info("[WIZARD] Creating local admin")
    create_local_admin_if_needed(
        db_name=db_name,
        root_cfg=root_cfg,
        username=username,
        email=email,
        password=raw_password,
    )

    logger.info("========== WIZARD IMPORT DONE ==========")

    return {
        "ok": True,
        "message": "Import terminé avec succès.",
        "prod": _is_prod(),
        "forced": force_import,
    }
