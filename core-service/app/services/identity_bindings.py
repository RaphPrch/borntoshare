"""Links between AD identities of BornToShare and their directory user (table identity_bindings).

Group roles, effective access and guardian checks go through these links: an AD identity is
linked to the directory user of the same source with the same objectGUID (external id), else
the same sAMAccountName (unique within a domain).
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

# Same matching rule as the backfill of schema/131_identity_source_service_accounts.sql
_SYNC_SQL = """
INSERT INTO identity_bindings (identity_id, directory_user_id)
SELECT i.id, du.id
FROM identities i
JOIN directory_users du
  ON du.identity_source_id = i.source_id
 AND (
   LOWER(TRIM(du.external_id)) = LOWER(TRIM(i.external_id))
   OR (du.object_guid IS NOT NULL AND LOWER(du.object_guid) = LOWER(TRIM(BOTH '}' FROM TRIM(BOTH '{' FROM i.external_id))))
   OR (du.username IS NOT NULL AND LOWER(du.username) = LOWER(i.username))
 )
WHERE LOWER(COALESCE(i.auth_source, '')) = 'ad'
  AND LOWER(COALESCE(i.type, 'user')) = 'user'
  AND (:source_id IS NULL OR i.source_id = :source_id)
  AND (:identity_id IS NULL OR i.id = :identity_id)
ON DUPLICATE KEY UPDATE deleted_at = NULL
"""


def sync_identity_bindings(db: Session, *, identity_source_id: int | None = None, identity_id: int | None = None) -> int:
    """Create the missing links (a source, an identity, or everything). The caller commits."""
    result = db.execute(
        text(_SYNC_SQL),
        {
            "source_id": int(identity_source_id) if identity_source_id else None,
            "identity_id": int(identity_id) if identity_id else None,
        },
    )
    return int(result.rowcount or 0)
