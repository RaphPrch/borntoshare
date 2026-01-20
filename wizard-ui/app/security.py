# backend/app/security.py

"""
BornToShare – Wizard Password Service
Compatible avec auth-service :
- Normalisation UTF-8 + troncature 72 bytes (bcrypt)
- Hash versionné :  b2s$v=1$bcrypt$<bcrypt_hash>
- Complexité stricte (> L2)
"""

import bcrypt
from fastapi import HTTPException

MAX_BCRYPT_LEN = 72


# ============================================================
# 🔐 COMPLEXITÉ (version wizard – stricte, L2/L3 compatible)
# ============================================================
def validate_password_complexity(password: str):
    """
    Règles renforcées BornToShare (wizard) :
    - Min 12 caractères
    - 1 minuscule
    - 1 majuscule
    - 1 chiffre
    - 1 spécial
    """
    if len(password) < 12:
        raise HTTPException(400, "Le mot de passe doit contenir au moins 12 caractères.")
    if not any(c.islower() for c in password):
        raise HTTPException(400, "Le mot de passe doit contenir une minuscule.")
    if not any(c.isupper() for c in password):
        raise HTTPException(400, "Le mot de passe doit contenir une majuscule.")
    if not any(c.isdigit() for c in password):
        raise HTTPException(400, "Le mot de passe doit contenir un chiffre.")
    if not any(not c.isalnum() for c in password):
        raise HTTPException(400, "Le mot de passe doit contenir un caractère spécial.")
    return True


# ============================================================
# 🧩 NORMALISATION BCRYPT
# ============================================================
def _normalize(password: str) -> bytes:
    """
    Normalise le password :
    - UTF-8
    - tronquage 72 bytes (limite bcrypt)
    """
    if password is None:
        raise ValueError("Password cannot be None")

    raw = password.encode("utf-8")
    return raw[:MAX_BCRYPT_LEN]


# ============================================================
# 🔐 HASH PASSWORD – FORMAT B2S OFFICIEL
# ============================================================
def get_password_hash(password: str) -> str:
    """
    Produit un hash NATIF 100 % compatible auth-service :
        b2s$v=1$bcrypt$<hash bcrypt>
    """

    validate_password_complexity(password)

    raw = _normalize(password)

    # bcrypt avec cost=12
    hashed = bcrypt.hashpw(raw, bcrypt.gensalt(rounds=12)).decode("utf-8")

    # Format versionné BornToShare
    return f"b2s$v=1$bcrypt${hashed}"
