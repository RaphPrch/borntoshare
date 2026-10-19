from __future__ import annotations

from sqlalchemy.orm import Session
from sqlalchemy.inspection import inspect as sa_inspect

from app.data.models.storage_root_access_profile import StorageRootAccessProfile
from app.utils.status_validation import (
    ensure_transition,
    normalize_status,
    validate_profile_invariants,
)


class StorageRootAccessProfilesRepo:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, profile_id: int) -> StorageRootAccessProfile | None:
        return (
            self.db.query(StorageRootAccessProfile)
            .filter(
                StorageRootAccessProfile.id == int(profile_id),
                StorageRootAccessProfile.deleted_at.is_(None),
            )
            .first()
        )

    def list_by_root(
        self,
        *,
        storage_root_id: int,
        access_level_code: str | None = None,
    ) -> list[StorageRootAccessProfile]:
        q = self.db.query(StorageRootAccessProfile).filter(
            StorageRootAccessProfile.storage_root_id == int(storage_root_id),
            StorageRootAccessProfile.deleted_at.is_(None),
        )
        if access_level_code is not None:
            q = q.filter(StorageRootAccessProfile.access_level_code == str(access_level_code).upper())
        return q.order_by(StorageRootAccessProfile.id.asc()).all()

    def find_by_root_and_permission_hash(
        self,
        *,
        storage_root_id: int,
        permission_hash: str,
    ) -> StorageRootAccessProfile | None:
        return (
            self.db.query(StorageRootAccessProfile)
            .filter(
                StorageRootAccessProfile.storage_root_id == int(storage_root_id),
                StorageRootAccessProfile.permission_hash == str(permission_hash),
                StorageRootAccessProfile.deleted_at.is_(None),
            )
            .first()
        )

    def create(self, *, data: dict) -> StorageRootAccessProfile:
        payload = dict(data)
        payload["status"] = normalize_status(payload.get("status") or "PENDING")
        validate_profile_invariants(
            status_value=payload.get("status"),
            group_external_id=payload.get("group_external_id"),
            error_code=payload.get("error_code"),
        )
        obj = StorageRootAccessProfile(**payload)
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def update(self, *, obj: StorageRootAccessProfile, updates: dict) -> StorageRootAccessProfile:
        payload = dict(updates)
        if "status" in payload:
            payload["status"] = ensure_transition(current=obj.status, next_status=payload.get("status"))

        validate_profile_invariants(
            status_value=payload.get("status") or obj.status,
            group_external_id=(
                payload.get("group_external_id")
                if "group_external_id" in payload
                else obj.group_external_id
            ),
            error_code=payload.get("error_code") if "error_code" in payload else obj.error_code,
        )

        for field, value in payload.items():
            setattr(obj, field, value)
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    @staticmethod
    def to_dict(obj: StorageRootAccessProfile) -> dict:
        mapper = sa_inspect(obj.__class__)
        return {col.key: getattr(obj, col.key) for col in mapper.columns}
