from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.inspection import inspect as sa_inspect

from app.models.storage_root_access_profile import StorageRootAccessProfile
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

    def list_active_storage_root_profile_candidates(
        self,
        *,
        storage_root_id: int,
        canonical_permission: str,
    ) -> list[dict]:
        level = "WRITE" if str(canonical_permission or "").strip().upper() == "WRITE" else "READ"
        rows = self.db.execute(
            text(
                """
                SELECT
                  srap.id AS storage_root_access_profile_id,
                  srap.access_profile_id AS access_profile_id,
                  UPPER(
                    COALESCE(
                      NULLIF(ap.code, ''),
                      NULLIF(ap.permission, ''),
                      :canonical_permission
                    )
                  ) AS access_profile_code,
                  COALESCE(NULLIF(srap.group_name, '')) AS group_ref,
                  COALESCE(NULLIF(srap.group_name, '')) AS group_name,
                  UPPER(COALESCE(NULLIF(srap.status, ''), 'QUEUED')) AS profile_status,
                  COALESCE(NULLIF(srap.group_external_id, '')) AS group_external_id,
                  se.identity_source_id AS identity_source_id,
                  COALESCE(
                    NULLIF(zpp.base_ou_dn, ''),
                    NULLIF(ids.default_group_ou_dn, '')
                  ) AS effective_group_ou_dn,
                  CASE
                    WHEN UPPER(
                      COALESCE(
                        NULLIF(srap.access_level_code, ''),
                        NULLIF(ap.code, ''),
                        NULLIF(ap.permission, ''),
                        'READ'
                      )
                    ) IN (
                      'WRITE',
                      'CONTRIBUTION',
                      'MODIFY',
                      'CHANGE',
                      'OWNER',
                      'ADMIN',
                      'FULL',
                      'FULLCONTROL',
                      'FULL_CONTROL',
                      'RW',
                      'RWX',
                      'READ_WRITE',
                      'READ-WRITE',
                      'WRITE_NTFS'
                    ) THEN 'WRITE'
                    ELSE 'READ'
                  END AS effective_permission
                FROM storage_root_access_profiles srap
                JOIN access_profiles ap ON ap.id = srap.access_profile_id
                JOIN storage_roots sr ON sr.id = srap.storage_root_id
                JOIN storage_endpoints se ON se.id = sr.storage_endpoint_id
                LEFT JOIN zone_provisioning_policy zpp ON zpp.zone_id = se.zone_id
                LEFT JOIN identity_sources ids ON ids.id = se.identity_source_id
                WHERE srap.storage_root_id = :storage_root_id
                  AND srap.deleted_at IS NULL
                  AND COALESCE(srap.active, 1) = 1
                  AND COALESCE(ap.active, 1) = 1
                GROUP BY
                  srap.id,
                  srap.access_profile_id,
                  ap.code,
                  ap.permission,
                  srap.group_name,
                  srap.status,
                  srap.group_external_id,
                  se.identity_source_id,
                  zpp.base_ou_dn,
                  ids.default_group_ou_dn,
                  srap.access_level_code
                HAVING effective_permission = :canonical_permission
                ORDER BY srap.id DESC
                """
            ),
            {
                "storage_root_id": int(storage_root_id),
                "canonical_permission": level,
            },
        ).mappings().all()
        return [dict(row) for row in rows]

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
