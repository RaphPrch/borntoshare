"""
BornToShare – Password Security Helpers (Wizard / Auth compatible)

- UTF-8 normalization + 72 bytes truncation (bcrypt)
- Versioned hash format: b2s$v=1$bcrypt$<bcrypt_hash>
- Strong password policy (L2/L3 compatible)

⚠️ This module MUST stay framework-agnostic
(no FastAPI / HTTP dependency).
"""

from __future__ import annotations

import bcrypt

MAX_BCRYPT_LEN = 72
BCRYPT_ROUNDS = 12


# ============================================================
# 🔐 PASSWORD COMPLEXITY
# ============================================================
def validate_password_complexity(password: str) -> None:
    """
    BornToShare strong password policy (wizard):

    - Minimum 12 characters
    - At least 1 lowercase
    - At least 1 uppercase
    - At least 1 digit
    - At least 1 special character

    Raises:
        ValueError if the password does not meet requirements.
    """
    if not password or not password.strip():
        raise ValueError("Password cannot be empty")

    if len(password) < 12:
        raise ValueError("Password must be at least 12 characters long")

    if not any(c.islower() for c in password):
        raise ValueError("Password must contain at least one lowercase letter")

    if not any(c.isupper() for c in password):
        raise ValueError("Password must contain at least one uppercase letter")

    if not any(c.isdigit() for c in password):
        raise ValueError("Password must contain at least one digit")

    if not any(not c.isalnum() for c in password):
        raise ValueError("Password must contain at least one special character")


# ============================================================
# 🧩 BCRYPT NORMALIZATION
# ============================================================
def _normalize_password(password: str) -> bytes:
    """
    Normalize password for bcrypt:
    - UTF-8 encoding
    - 72 bytes truncation (bcrypt hard limit)
    """
    if not password or not password.strip():
        raise ValueError("Password cannot be empty")

    raw = password.encode("utf-8")
    return raw[:MAX_BCRYPT_LEN]


# ============================================================
# 🔐 HASH PASSWORD – OFFICIAL B2S FORMAT
# ============================================================
def hash_password_b2s(password: str, *, validate: bool = True) -> str:
    """
    Generate a BornToShare versioned password hash.

    Format:
        b2s$v=1$bcrypt$<bcrypt_hash>

    Args:
        password: clear text password
        validate: enforce complexity rules (default: True)

    Returns:
        Versioned B2S password hash
    """
    if validate:
        validate_password_complexity(password)

    raw = _normalize_password(password)

    hashed = bcrypt.hashpw(
        raw,
        bcrypt.gensalt(rounds=BCRYPT_ROUNDS),
    ).decode("utf-8")

    return f"b2s$v=1$bcrypt${hashed}"
