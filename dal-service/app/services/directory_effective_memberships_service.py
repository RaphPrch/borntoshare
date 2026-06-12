from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.repositories.directory_effective_memberships_repo import DirectoryEffectiveMembershipsRepo


class DirectoryEffectiveMembershipsService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = DirectoryEffectiveMembershipsRepo(db)

    def rebuild_for_snapshot(self, *, snapshot_id: int) -> dict[str, Any]:
        return self.repo.rebuild_for_snapshot(int(snapshot_id))

    def rebuild_for_identity_source(self, *, identity_source_id: int) -> dict[str, Any]:
        return self.repo.rebuild_for_identity_source(int(identity_source_id))

    def rebuild_all_active(self) -> list[dict[str, Any]]:
        return self.repo.rebuild_all_active()

