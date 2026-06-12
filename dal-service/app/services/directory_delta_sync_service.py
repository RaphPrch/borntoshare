from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.services.directory_snapshot_service import DirectorySnapshotService


class DirectoryDeltaSyncService:
    def __init__(self, db: Session):
        self.db = db
        self.snapshot_service = DirectorySnapshotService(db)

    def run(
        self,
        *,
        identity_source_id: int,
        initiated_by: str | None,
        snapshot_source: str | None,
        correlation_id: str | None,
        preferred_mode: str | None = "auto",
        force_full: bool = False,
    ) -> dict[str, Any]:
        return self.snapshot_service.run_snapshot(
            identity_source_id=int(identity_source_id),
            initiated_by=initiated_by,
            snapshot_source=snapshot_source,
            correlation_id=correlation_id,
            mode=preferred_mode,
            force_full=bool(force_full),
        )

