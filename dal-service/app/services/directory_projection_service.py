from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.repositories.directory_snapshots_repo import DirectorySnapshotsRepo


class DirectoryProjectionService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = DirectorySnapshotsRepo(db)

    def activate_snapshot(self, *, snapshot_id: int, activated_by: str | None = None) -> dict[str, Any] | None:
        return self.repo.activate(snapshot_id=int(snapshot_id), activated_by=activated_by)

