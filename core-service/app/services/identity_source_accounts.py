"""Service accounts per capability of an identity source (table identity_source_service_accounts).

snapshot     : reads the directory (snapshot collection, live search)
auth         : finds the user being authenticated (auth-service)
provisioning : creates AD groups and changes their members (capsule-runner)

A capability without its own account uses the account of the source (bind_dn / bind_password_ref).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

PURPOSES = ("snapshot", "auth", "provisioning")


def load_accounts(db: Session, source_id: int) -> dict[str, dict[str, str]]:
    """Dedicated accounts of a source, by purpose (only the purposes that have one)."""
    try:
        rows = db.execute(
            text(
                """
                SELECT purpose, bind_dn, bind_password_ref
                FROM identity_source_service_accounts
                WHERE identity_source_id = :source_id
                """
            ),
            {"source_id": int(source_id)},
        ).mappings().all()
    except Exception:
        # Schema not migrated yet: every capability uses the account of the source
        db.rollback()
        return {}
    return {
        str(row["purpose"]): {"bind_dn": str(row["bind_dn"]), "bind_password_ref": str(row["bind_password_ref"])}
        for row in rows
        if str(row["purpose"]) in PURPOSES
    }


def save_accounts(db: Session, source_id: int, accounts: dict[str, Any]) -> None:
    """Set or remove dedicated accounts. The caller commits.

    accounts: {purpose: {"bind_dn": ..., "bind_password_ref": ...} | None}
      - None or an empty bind_dn removes the dedicated account (back to the account of the source)
      - a missing bind_password_ref keeps the stored secret (bind DN change only)
    """
    current = load_accounts(db, source_id)
    for purpose, account in (accounts or {}).items():
        if purpose not in PURPOSES:
            raise ValueError(f"Unknown service account purpose: {purpose}")
        bind_dn = str((account or {}).get("bind_dn") or "").strip()
        if not bind_dn:
            db.execute(
                text("DELETE FROM identity_source_service_accounts WHERE identity_source_id = :sid AND purpose = :purpose"),
                {"sid": int(source_id), "purpose": purpose},
            )
            continue
        ref = str((account or {}).get("bind_password_ref") or "").strip() or current.get(purpose, {}).get("bind_password_ref")
        if not ref:
            raise ValueError(f"A password is required for the {purpose} service account")
        db.execute(
            text(
                """
                INSERT INTO identity_source_service_accounts (identity_source_id, purpose, bind_dn, bind_password_ref)
                VALUES (:sid, :purpose, :bind_dn, :ref)
                ON DUPLICATE KEY UPDATE bind_dn = VALUES(bind_dn), bind_password_ref = VALUES(bind_password_ref)
                """
            ),
            {"sid": int(source_id), "purpose": purpose, "bind_dn": bind_dn, "ref": ref},
        )


def account_for(source: dict[str, Any], purpose: str) -> tuple[str | None, str | None]:
    """(bind_dn, bind_password_ref) to use for a capability: its own account, else the account of the source."""
    dedicated = ((source or {}).get("service_accounts") or {}).get(purpose) or {}
    if dedicated.get("bind_dn") and dedicated.get("bind_password_ref"):
        return str(dedicated["bind_dn"]), str(dedicated["bind_password_ref"])
    return (source or {}).get("bind_dn") or None, (source or {}).get("bind_password_ref") or None


def public_accounts(accounts: dict[str, dict[str, str]]) -> dict[str, dict[str, Any]]:
    """Accounts for the UI: bind DN and whether a password is stored, never the reference."""
    return {
        purpose: {"bind_dn": account.get("bind_dn"), "has_password": bool(account.get("bind_password_ref"))}
        for purpose, account in accounts.items()
    }
