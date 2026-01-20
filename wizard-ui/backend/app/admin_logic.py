"""
BornToShare – Wizard Admin Creator
---------------------------------
Création d’un administrateur LOCAL dans la DAL V1.

Compatible avec :
 - identity / local_credential
 - hash BornToShare versionné
 - wizard DEV uniquement
 - bcrypt (12 rounds)
"""

import bcrypt
from app.db import get_connection

BCRYPT_ROUNDS = 12
MAX_BCRYPT_LEN = 72  # Limite bcrypt


# ============================================================
# 🧩 Normalisation bcrypt (72 bytes max)
# ============================================================
def _normalize_password(password: str) -> bytes:
    if not password:
        raise ValueError("Password cannot be empty")
    raw = password.encode("utf-8")
    return raw[:MAX_BCRYPT_LEN]


# ============================================================
# 🔐 Hash BornToShare versionné
# ============================================================
def hash_password_b2s(password: str) -> str:
    """
    Hash format BornToShare :
        b2s$v=1$bcrypt$<bcrypt_hash>
    Reconnu par auth-service.verify_password()
    """
    raw = _normalize_password(password)
    hashed = bcrypt.hashpw(raw, bcrypt.gensalt(rounds=BCRYPT_ROUNDS))
    return f"b2s$v=1$bcrypt${hashed.decode('utf-8')}"


# ============================================================
# 👑 Création admin LOCAL (idempotent)
# ============================================================
def create_admin_if_needed(
    *,
    db_name: str,
    root_cfg: dict,
    username: str,
    email: str,
    password: str,
):
    """
    Crée un administrateur LOCAL si absent.

    - table : identity
    - credentials : local_credential
    - utilisé uniquement par le wizard
    """

    conn = get_connection(database=True, db_name=db_name, root_cfg=root_cfg)
    cur = conn.cursor()

    try:
        # 1) Récupérer ou créer l'identité "admin" (local)
        cur.execute(
            """
            SELECT id
            FROM identity
            WHERE identity_type = 'local'
              AND username = %s
            LIMIT 1
            """,
            (username,),
        )
        row = cur.fetchone()

        if row:
            identity_id = int(row[0])
            # Optionnel : synchroniser quelques champs "profil"
            cur.execute(
                """
                UPDATE identity
                SET email = COALESCE(%s, email),
                    display_name = COALESCE(%s, display_name),
                    is_active = 1
                WHERE id = %s
                """,
                (email, username, identity_id),
            )
        else:
            cur.execute(
                """
                INSERT INTO identity (
                    identity_type,
                    username,
                    email,
                    display_name,
                    is_active
                )
                VALUES ('local', %s, %s, %s, 1)
                """,
                (username, email, username),
            )
            identity_id = int(cur.lastrowid)

        # 2) Upsert du credential local : on applique TOUJOURS le mot de passe choisi dans le wizard
        pwd_hash = hash_password_b2s(password)
        cur.execute(
            """
            SELECT identity_id
            FROM local_credential
            WHERE identity_id = %s
            LIMIT 1
            """,
            (identity_id,),
        )
        has_cred = cur.fetchone() is not None

        if has_cred:
            cur.execute(
                """
                UPDATE local_credential
                SET password_hash = %s,
                    password_algo = 'bcrypt'
                WHERE identity_id = %s
                """,
                (pwd_hash, identity_id),
            )
        else:
            cur.execute(
                """
                INSERT INTO local_credential (
                    identity_id,
                    password_hash,
                    password_algo
                )
                VALUES (%s, %s, 'bcrypt')
                """,
                (identity_id, pwd_hash),
            )

        conn.commit()

    finally:
        cur.close()
        conn.close()
