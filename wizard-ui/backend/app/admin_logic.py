"""
BornToShare – Wizard Admin Bootstrap
-----------------------------------
Création / synchronisation d’un administrateur LOCAL
via le Wizard uniquement.

⚠️ ATTENTION
- DEV / BOOTSTRAP ONLY
- Ne doit JAMAIS être exposé comme API publique
- À exécuter une seule fois (initialisation)
"""

from __future__ import annotations

import bcrypt
import logging

from .db import get_connection

logger = logging.getLogger("wizard.admin")

BCRYPT_ROUNDS = 12
MAX_BCRYPT_LEN = 72  # Limite bcrypt stricte


# ============================================================
# 🔐 Password helpers
# ============================================================

def _normalize_password(password: str) -> bytes:
    """
    Normalise le mot de passe pour bcrypt (72 bytes max).
    """
    if not password or not password.strip():
        raise ValueError("Password cannot be empty")

    raw = password.encode("utf-8")
    return raw[:MAX_BCRYPT_LEN]


def hash_password_b2s(password: str) -> str:
    """
    Hash BornToShare versionné.

    Format :
      b2s$v=1$bcrypt$<hash>

    Compatible avec auth-service.verify_password()
    """
    raw = _normalize_password(password)
    hashed = bcrypt.hashpw(raw, bcrypt.gensalt(rounds=BCRYPT_ROUNDS))
    return f"b2s$v=1$bcrypt${hashed.decode('utf-8')}"


# ============================================================
# 👑 Admin bootstrap (WIZARD ONLY)
# ============================================================

def create_local_admin_if_needed(
    *,
    db_name: str,
    root_cfg: dict,
    username: str,
    email: str,
    password: str,
) -> None:
    """
    Crée ou synchronise un administrateur LOCAL.

    - identities.auth_source = 'local'
    - local_credentials (bcrypt)
    - idempotent
    - mot de passe TOUJOURS mis à jour

    À utiliser UNIQUEMENT depuis le wizard.
    """

    if not username:
        raise ValueError("username is required")

    conn = get_connection(database=True, db_name=db_name, root_cfg=root_cfg)
    cur = conn.cursor()

    try:
        logger.info("[ADMIN] Ensuring local admin '%s'", username)

        # ----------------------------------------------------
        # Identity source (local)
        # ----------------------------------------------------
        cur.execute(
            """
            SELECT id
            FROM identity_sources
            WHERE type = 'local'
            LIMIT 1
            """
        )
        src_row = cur.fetchone()
        if src_row:
            source_id = int(src_row[0])
        else:
            cur.execute(
                """
                INSERT INTO identity_sources (
                    type,
                    name,
                    capabilities,
                    is_active,
                    status
                )
                VALUES ('local', %s, %s, 1, 'active')
                """,
                ("Local", '{"auth": true, "import_groups": false, "auth_mode": "local"}'),
            )
            source_id = int(cur.lastrowid)

        # ----------------------------------------------------
        # Identity
        # ----------------------------------------------------
        cur.execute(
            """
            SELECT id
            FROM identities
            WHERE auth_source = 'local'
              AND username = %s
            LIMIT 1
            """,
            (username,),
        )
        row = cur.fetchone()

        if row:
            identity_id = int(row[0])
            cur.execute(
                """
                UPDATE identities
                SET email = COALESCE(%s, email),
                    display_name = COALESCE(%s, display_name),
                    is_active = 1,
                    auth_source = 'local',
                    provisioning_source = 'system'
                WHERE id = %s
                """,
                (email, username, identity_id),
            )
            logger.info("[ADMIN] Existing identity updated (id=%s)", identity_id)
        else:
            cur.execute(
                """
                INSERT INTO identities (
                    source_id,
                    username,
                    type,
                    external_id,
                    email,
                    display_name,
                    auth_source,
                    is_active,
                    provisioning_source
                )
                VALUES (%s, %s, 'user', %s, %s, %s, 'local', 1, 'system')
                """,
                (source_id, username, username, email, username),
            )
            identity_id = int(cur.lastrowid)
            logger.info("[ADMIN] New identity created (id=%s)", identity_id)

        # ----------------------------------------------------
        # RBAC bootstrap (platform_admin direct grant)
        # ----------------------------------------------------
        cur.execute(
            """
            INSERT INTO roles (code, label, description)
            VALUES
              ('user', 'User', 'Standard application access within BornToShare'),
              ('platform_admin', 'Platform administrator', 'Full administrative access within BornToShare')
            ON DUPLICATE KEY UPDATE
              label = VALUES(label),
              description = VALUES(description)
            """
        )

        cur.execute(
            """
            SELECT id
            FROM roles
            WHERE code = 'platform_admin'
            LIMIT 1
            """
        )
        role_row = cur.fetchone()
        if not role_row:
            raise RuntimeError("platform_admin role missing after RBAC bootstrap")
        platform_admin_role_id = int(role_row[0])

        cur.execute(
            """
            SELECT 1
            FROM identity_roles
            WHERE identity_id = %s
              AND role_id = %s
            LIMIT 1
            """,
            (identity_id, platform_admin_role_id),
        )
        if not cur.fetchone():
            cur.execute(
                """
                INSERT INTO identity_roles (
                    identity_id,
                    directory_group_id,
                    role_id,
                    source
                )
                VALUES (%s, NULL, %s, 'bootstrap')
                """,
                (identity_id, platform_admin_role_id),
            )
            logger.info("[ADMIN] platform_admin grant created for identity id=%s", identity_id)

        # ----------------------------------------------------
        # Credentials (always updated)
        # ----------------------------------------------------
        pwd_hash = hash_password_b2s(password)

        cur.execute(
            """
            SELECT 1
            FROM local_credentials
            WHERE identity_id = %s
            LIMIT 1
            """,
            (identity_id,),
        )

        if cur.fetchone():
            cur.execute(
                """
                UPDATE local_credentials
                SET password_hash = %s,
                    password_version = 'b2s$v=1$bcrypt',
                    last_rotated_at = NOW(6)
                WHERE identity_id = %s
                """,
                (pwd_hash, identity_id),
            )
            logger.info("[ADMIN] Credential updated")
        else:
            cur.execute(
                """
                INSERT INTO local_credentials (
                    identity_id,
                    password_hash,
                    password_version,
                    last_rotated_at
                )
                VALUES (%s, %s, 'b2s$v=1$bcrypt', NOW(6))
                """,
                (identity_id, pwd_hash),
            )
            logger.info("[ADMIN] Credential created")

        conn.commit()

    except Exception:
        conn.rollback()
        logger.exception("[ADMIN] Failed to bootstrap admin")
        raise

    finally:
        cur.close()
        conn.close()
