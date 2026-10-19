from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


class StorageRootOwnersRepo:
    """Write repository for storage root owners assignments."""

    def __init__(self, db: Session):
        self.db = db

    def replace_owners(
        self,
        *,
        storage_root_id: int,
        guardian_ids: list[int],
        assigned_by: int | None = None,
    ) -> None:
        root_id = int(storage_root_id)
        guardians = {int(v) for v in guardian_ids if int(v) > 0}

        self.db.execute(
            text(
                """
                DELETE FROM storage_root_roles
                WHERE root_id = :storage_root_id
                  AND LOWER(role) = 'guardian'
                """
            ),
            {"storage_root_id": root_id},
        )

        for identity_id in sorted(guardians):
            self.db.execute(
                text(
                    """
                    INSERT INTO storage_root_roles (root_id, identity_id, role, assigned_by)
                    VALUES (:storage_root_id, :identity_id, 'guardian', :assigned_by)
                    """
                ),
                {
                    "storage_root_id": root_id,
                    "identity_id": identity_id,
                    "assigned_by": assigned_by,
                },
            )
