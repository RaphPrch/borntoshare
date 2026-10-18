from __future__ import annotations

from typing import List

from sqlalchemy import text


class IdentityRolesRepo:
    """RBAC effective roles resolver (SQL-first, V1++).

    Contract:
    - Input: identity_id (BIGINT)
    - Output: list[str] of role codes (deduplicated)

    Notes:
    - Roles are assigned either directly to identities (identity_roles.identity_id)
      or to directory groups (identity_roles.directory_group_id).
    - Group membership source of truth is `directory_group_members`.
    """

    def __init__(self, db):
        self.db = db

    def get_effective_role_codes(self, identity_id: int) -> List[str]:
        res = self.db.execute(
            text(
                """
                SELECT DISTINCT role_code
                FROM v_identity_effective_roles
                WHERE identity_id = :identity_id
                ORDER BY role_code
                """
            ),
            {"identity_id": int(identity_id)},
        )

        return [str(r[0]) for r in res.fetchall()]

