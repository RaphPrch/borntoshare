from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.naming_policy import resolve_group_name


CANONICAL_PERMISSIONS: tuple[str, str] = ("READ", "WRITE")


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def normalize_permission(value: str | None) -> str | None:
    raw = str(value or "").strip().upper()
    if not raw:
        return None
    if raw in {"READ", "READ_NTFS", "AUDIT", "READ_ONLY", "READ-ONLY"}:
        return "READ"
    if raw in {
        "WRITE",
        "WRITE_NTFS",
        "CONTRIBUTION",
        "MODIFY",
        "RW",
        "RWX",
        "READ_WRITE",
        "READ-WRITE",
        "CHANGE",
        "OWNER",
        "ADMIN",
        "FULL",
        "FULLCONTROL",
        "FULL_CONTROL",
    }:
        return "WRITE"
    return None


@dataclass(frozen=True)
class MaterializationCandidate:
    permission: str
    access_profile_id: int
    profile_code: str | None
    profile_name: str | None
    source: str


@dataclass(frozen=True)
class PermissionComputation:
    permission: str
    status: str
    resolved: MaterializationCandidate | None
    candidates: list[MaterializationCandidate]


@dataclass
class RootBindingsMaterializationReport:
    storage_root_id: int
    zone_id: int | None
    created_rows: int = 0
    updated_rows: int = 0
    deactivated_rows: int = 0
    unchanged_rows: int = 0
    repaired: bool = False
    expected_permissions: list[str] | None = None
    missing_permissions: list[str] | None = None
    ambiguity_warnings: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        expected = sorted({str(v).upper() for v in (self.expected_permissions or []) if str(v).strip()})
        missing = sorted({str(v).upper() for v in (self.missing_permissions or []) if str(v).strip()})
        warnings = [str(v) for v in (self.ambiguity_warnings or []) if str(v).strip()]
        return {
            "storage_root_id": int(self.storage_root_id),
            "zone_id": int(self.zone_id) if self.zone_id else None,
            "created_rows": int(self.created_rows),
            "updated_rows": int(self.updated_rows),
            "deactivated_rows": int(self.deactivated_rows),
            "unchanged_rows": int(self.unchanged_rows),
            "repaired": bool(self.repaired),
            "expected_permissions": expected,
            "missing_permissions": missing,
            "ambiguity_warnings": warnings,
            "approval_ready": len(missing) == 0 and len(warnings) == 0,
        }


def _root_context(db: Session, *, storage_root_id: int) -> dict[str, Any] | None:
    return db.execute(
        text(
            """
            SELECT
              sr.id AS storage_root_id,
              sr.root_path AS root_path,
              se.zone_id AS zone_id
            FROM storage_roots sr
            JOIN storage_endpoints se ON se.id = sr.storage_endpoint_id
            WHERE sr.id = :storage_root_id
            LIMIT 1
            """
        ),
        {"storage_root_id": int(storage_root_id)},
    ).mappings().first()


def list_effective_zone_profile_candidates_for_root(
    db: Session,
    *,
    storage_root_id: int,
) -> list[MaterializationCandidate]:
    rows = db.execute(
        text(
            """
            SELECT
              zap.access_profile_id,
              ap.code AS profile_code,
              ap.name AS profile_name,
              UPPER(
                COALESCE(
                  NULLIF(ap.code, ''),
                  NULLIF(ap.permission, ''),
                  'READ'
                )
              ) AS permission_candidate
            FROM storage_roots sr
            JOIN storage_endpoints se ON se.id = sr.storage_endpoint_id
            JOIN zone_access_profiles zap
              ON zap.zone_id = se.zone_id
             AND zap.is_active = 1
            JOIN access_profiles ap
              ON ap.id = zap.access_profile_id
             AND COALESCE(ap.active, 1) = 1
            WHERE sr.id = :storage_root_id
            """
        ),
        {"storage_root_id": int(storage_root_id)},
    ).mappings().all()

    out: list[MaterializationCandidate] = []
    for row in rows:
        permission = normalize_permission(str(row.get("permission_candidate") or ""))
        profile_id = int(row.get("access_profile_id") or 0)
        if permission not in {"READ", "WRITE"} or profile_id <= 0:
            continue
        out.append(
            MaterializationCandidate(
                permission=permission,
                access_profile_id=profile_id,
                profile_code=str(row.get("profile_code") or "").strip() or None,
                profile_name=str(row.get("profile_name") or "").strip() or None,
                source="ZONE",
            )
        )
    return out


def _list_explicit_root_candidates(db: Session, *, storage_root_id: int) -> list[MaterializationCandidate]:
    rows = db.execute(
        text(
            """
            SELECT
              srap.access_profile_id,
              ap.code AS profile_code,
              ap.name AS profile_name,
              UPPER(
                COALESCE(
                  NULLIF(srap.access_level_code, ''),
                  NULLIF(ap.code, ''),
                  NULLIF(ap.permission, ''),
                  'READ'
                )
              ) AS permission_candidate,
              UPPER(COALESCE(NULLIF(srap.source, ''), 'LOCAL')) AS source
            FROM storage_root_access_profiles srap
            JOIN access_profiles ap ON ap.id = srap.access_profile_id
            WHERE srap.storage_root_id = :storage_root_id
              AND srap.deleted_at IS NULL
              AND COALESCE(srap.active, 1) = 1
              AND COALESCE(ap.active, 1) = 1
            """
        ),
        {"storage_root_id": int(storage_root_id)},
    ).mappings().all()

    out: list[MaterializationCandidate] = []
    for row in rows:
        source = str(row.get("source") or "LOCAL").strip().upper()
        if source not in {"LOCAL", "MANUAL", "EXPLICIT"}:
            continue
        permission = normalize_permission(str(row.get("permission_candidate") or ""))
        profile_id = int(row.get("access_profile_id") or 0)
        if permission not in {"READ", "WRITE"} or profile_id <= 0:
            continue
        out.append(
            MaterializationCandidate(
                permission=permission,
                access_profile_id=profile_id,
                profile_code=str(row.get("profile_code") or "").strip() or None,
                profile_name=str(row.get("profile_name") or "").strip() or None,
                source="LOCAL",
            )
        )
    return out


def compute_effective_root_bindings(
    db: Session,
    *,
    storage_root_id: int,
) -> dict[str, PermissionComputation]:
    explicit = _list_explicit_root_candidates(db, storage_root_id=int(storage_root_id))
    inherited = list_effective_zone_profile_candidates_for_root(db, storage_root_id=int(storage_root_id))

    out: dict[str, PermissionComputation] = {}
    for permission in CANONICAL_PERMISSIONS:
        explicit_candidates = [row for row in explicit if row.permission == permission]
        inherited_candidates = [row for row in inherited if row.permission == permission]

        if len(explicit_candidates) > 1:
            out[permission] = PermissionComputation(
                permission=permission,
                status="ambiguous",
                resolved=None,
                candidates=explicit_candidates,
            )
            continue

        if len(explicit_candidates) == 1:
            out[permission] = PermissionComputation(
                permission=permission,
                status="resolved",
                resolved=explicit_candidates[0],
                candidates=explicit_candidates,
            )
            continue

        if len(inherited_candidates) > 1:
            out[permission] = PermissionComputation(
                permission=permission,
                status="ambiguous",
                resolved=None,
                candidates=inherited_candidates,
            )
            continue

        if len(inherited_candidates) == 1:
            out[permission] = PermissionComputation(
                permission=permission,
                status="resolved",
                resolved=inherited_candidates[0],
                candidates=inherited_candidates,
            )
            continue

        out[permission] = PermissionComputation(
            permission=permission,
            status="missing",
            resolved=None,
            candidates=[],
        )

    return out


def _expected_group_name(
    db: Session,
    *,
    root_path: str,
    zone_id: int | None,
    permission: str,
    profile_code: str | None,
) -> str | None:
    group_name = ""
    try:
        naming = resolve_group_name(
            db,
            zone_ref=zone_id,
            storage_root_path=str(root_path or ""),
            perm=str(permission or "READ"),
            profile=str(profile_code or permission),
        )
        group_name = str((naming or {}).get("samAccountName") or "").strip()
    except Exception:
        group_name = ""

    if group_name:
        return group_name[:128]
    return None


def _list_active_rows_for_permission(
    db: Session,
    *,
    storage_root_id: int,
    permission: str,
) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            """
            SELECT
              srap.id,
              srap.storage_root_id,
              srap.access_profile_id,
              UPPER(COALESCE(NULLIF(srap.source, ''), 'ZONE')) AS source,
              srap.group_name,
              srap.group_external_id,
              UPPER(COALESCE(NULLIF(srap.status, ''), 'QUEUED')) AS status,
              UPPER(
                COALESCE(
                  NULLIF(srap.access_level_code, ''),
                  NULLIF(ap.code, ''),
                  NULLIF(ap.permission, ''),
                  'READ'
                )
              ) AS permission_candidate
            FROM storage_root_access_profiles srap
            JOIN access_profiles ap ON ap.id = srap.access_profile_id
            WHERE srap.storage_root_id = :storage_root_id
              AND srap.deleted_at IS NULL
              AND COALESCE(srap.active, 1) = 1
              AND COALESCE(ap.active, 1) = 1
            ORDER BY
              CASE WHEN NULLIF(srap.group_external_id, '') IS NOT NULL THEN 0 ELSE 1 END,
              srap.id ASC
            """
        ),
        {"storage_root_id": int(storage_root_id)},
    ).mappings().all()

    out: list[dict[str, Any]] = []
    for row in rows:
        normalized = normalize_permission(str(row.get("permission_candidate") or ""))
        if normalized != permission:
            continue
        out.append(dict(row))
    return out


def materialize_root_bindings(
    db: Session,
    *,
    storage_root_id: int,
    replace_stale: bool = True,
    commit: bool = True,
) -> RootBindingsMaterializationReport:
    root = _root_context(db, storage_root_id=int(storage_root_id))
    if root is None:
        return RootBindingsMaterializationReport(
            storage_root_id=int(storage_root_id),
            zone_id=None,
            missing_permissions=["READ", "WRITE"],
            ambiguity_warnings=["storage_root_not_found"],
        )

    zone_id = int(root.get("zone_id") or 0) or None
    root_path = str(root.get("root_path") or "")

    computation = compute_effective_root_bindings(db, storage_root_id=int(storage_root_id))
    expected_permissions = [permission for permission, result in computation.items() if result.status != "missing"]
    if not expected_permissions:
        expected_permissions = ["READ", "WRITE"]

    report = RootBindingsMaterializationReport(
        storage_root_id=int(storage_root_id),
        zone_id=zone_id,
        expected_permissions=expected_permissions,
        missing_permissions=[],
        ambiguity_warnings=[],
    )

    now = _utcnow_naive()

    for permission in expected_permissions:
        result = computation.get(permission)
        if result is None:
            continue

        active_rows_for_permission = _list_active_rows_for_permission(
            db,
            storage_root_id=int(storage_root_id),
            permission=permission,
        )

        if result.status == "ambiguous":
            report.ambiguity_warnings = (report.ambiguity_warnings or []) + [
                f"ambiguous_{permission.lower()}"
            ]
            continue

        if result.status != "resolved" or result.resolved is None:
            report.missing_permissions = (report.missing_permissions or []) + [permission]
            if replace_stale:
                for stale in active_rows_for_permission:
                    stale_id = int(stale.get("id") or 0)
                    if stale_id <= 0:
                        continue
                    db.execute(
                        text(
                            """
                            UPDATE storage_root_access_profiles
                            SET active = 0,
                                deleted_at = COALESCE(deleted_at, :deleted_at),
                                updated_at = CURRENT_TIMESTAMP
                            WHERE id = :id
                            """
                        ),
                        {"id": int(stale_id), "deleted_at": now},
                    )
                    report.deactivated_rows += 1
            continue

        candidate = result.resolved
        expected_group_name = _expected_group_name(
            db,
            root_path=root_path,
            zone_id=zone_id,
            permission=permission,
            profile_code=candidate.profile_code,
        )

        active_rows = active_rows_for_permission

        keep_row = next((row for row in active_rows if int(row.get("access_profile_id") or 0) == int(candidate.access_profile_id)), None)
        if keep_row is None and active_rows:
            keep_row = active_rows[0]

        if expected_group_name is None and keep_row is None:
            report.missing_permissions = (report.missing_permissions or []) + [permission]
            continue

        keeper_id = int(keep_row.get("id") or 0) if keep_row else 0
        if keeper_id > 0:
            current_group_name = str(keep_row.get("group_name") or "").strip()
            next_group_name = expected_group_name or current_group_name
            current_source = str(keep_row.get("source") or "ZONE").strip().upper()
            current_profile_id = int(keep_row.get("access_profile_id") or 0)
            changed = (
                current_profile_id != int(candidate.access_profile_id)
                or str(next_group_name or "") != str(current_group_name or "")
                or current_source != str(candidate.source).upper()
            )

            db.execute(
                text(
                    """
                    UPDATE storage_root_access_profiles
                    SET access_profile_id = :access_profile_id,
                        access_level_code = :access_level_code,
                        source = :source,
                        group_name = :group_name,
                        active = 1,
                        deleted_at = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                    """
                ),
                {
                    "id": int(keeper_id),
                    "access_profile_id": int(candidate.access_profile_id),
                    "access_level_code": permission,
                    "source": str(candidate.source).upper(),
                    "group_name": str(next_group_name),
                },
            )
            if changed:
                report.updated_rows += 1
            else:
                report.unchanged_rows += 1
        else:
            db.execute(
                text(
                    """
                    INSERT INTO storage_root_access_profiles (
                      storage_root_id,
                      access_profile_id,
                      source,
                      group_name,
                      access_level_code,
                      status,
                      active,
                      deleted_at
                    ) VALUES (
                      :storage_root_id,
                      :access_profile_id,
                      :source,
                      :group_name,
                      :access_level_code,
                      'QUEUED',
                      1,
                      NULL
                    )
                    """
                ),
                {
                    "storage_root_id": int(storage_root_id),
                    "access_profile_id": int(candidate.access_profile_id),
                    "source": str(candidate.source).upper(),
                    "group_name": str(expected_group_name),
                    "access_level_code": permission,
                },
            )
            report.created_rows += 1

        if replace_stale:
            stale_ids = [
                int(row.get("id") or 0)
                for row in active_rows
                if int(row.get("id") or 0) > 0 and int(row.get("id") or 0) != int(keeper_id)
            ]
            for stale_id in stale_ids:
                db.execute(
                    text(
                        """
                        UPDATE storage_root_access_profiles
                        SET active = 0,
                            deleted_at = COALESCE(deleted_at, :deleted_at),
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :id
                        """
                    ),
                    {"id": int(stale_id), "deleted_at": now},
                )
                report.deactivated_rows += 1

    report.repaired = (report.created_rows + report.updated_rows + report.deactivated_rows) > 0

    if commit:
        db.commit()
    return report


def repair_missing_root_bindings(
    db: Session,
    *,
    storage_root_id: int,
    commit: bool = True,
) -> RootBindingsMaterializationReport:
    return materialize_root_bindings(
        db,
        storage_root_id=int(storage_root_id),
        replace_stale=True,
        commit=commit,
    )


def resync_roots_for_zone(
    db: Session,
    *,
    zone_id: int,
    replace_stale: bool = True,
    commit: bool = True,
) -> dict[str, Any]:
    rows = db.execute(
        text(
            """
            SELECT sr.id
            FROM storage_roots sr
            JOIN storage_endpoints se ON se.id = sr.storage_endpoint_id
            WHERE se.zone_id = :zone_id
            ORDER BY sr.id ASC
            """
        ),
        {"zone_id": int(zone_id)},
    ).mappings().all()

    reports: list[dict[str, Any]] = []
    total_created = 0
    total_updated = 0
    total_deactivated = 0
    total_unchanged = 0
    total_repaired = 0
    root_ids: list[int] = []

    for row in rows:
        root_id = int(row.get("id") or 0)
        if root_id <= 0:
            continue
        root_ids.append(root_id)
        report = materialize_root_bindings(
            db,
            storage_root_id=root_id,
            replace_stale=replace_stale,
            commit=False,
        )
        payload = report.to_dict()
        reports.append(payload)
        total_created += int(payload.get("created_rows") or 0)
        total_updated += int(payload.get("updated_rows") or 0)
        total_deactivated += int(payload.get("deactivated_rows") or 0)
        total_unchanged += int(payload.get("unchanged_rows") or 0)
        if bool(payload.get("repaired")):
            total_repaired += 1

    if commit:
        db.commit()

    return {
        "zone_id": int(zone_id),
        "roots_count": len(root_ids),
        "root_ids": root_ids,
        "reports": reports,
        "created_rows": total_created,
        "updated_rows": total_updated,
        "deactivated_rows": total_deactivated,
        "unchanged_rows": total_unchanged,
        "repaired_roots": total_repaired,
    }


def repair_all_root_bindings(
    db: Session,
    *,
    replace_stale: bool = True,
    commit: bool = True,
) -> dict[str, Any]:
    rows = db.execute(text("SELECT id FROM storage_roots ORDER BY id ASC")).mappings().all()
    reports: list[dict[str, Any]] = []
    total_created = 0
    total_updated = 0
    total_deactivated = 0
    total_unchanged = 0
    total_repaired = 0
    root_ids: list[int] = []

    for row in rows:
        root_id = int(row.get("id") or 0)
        if root_id <= 0:
            continue
        root_ids.append(root_id)
        report = materialize_root_bindings(
            db,
            storage_root_id=root_id,
            replace_stale=replace_stale,
            commit=False,
        )
        payload = report.to_dict()
        reports.append(payload)
        total_created += int(payload.get("created_rows") or 0)
        total_updated += int(payload.get("updated_rows") or 0)
        total_deactivated += int(payload.get("deactivated_rows") or 0)
        total_unchanged += int(payload.get("unchanged_rows") or 0)
        if bool(payload.get("repaired")):
            total_repaired += 1

    if commit:
        db.commit()

    return {
        "roots_count": len(root_ids),
        "root_ids": root_ids,
        "reports": reports,
        "created_rows": total_created,
        "updated_rows": total_updated,
        "deactivated_rows": total_deactivated,
        "unchanged_rows": total_unchanged,
        "repaired_roots": total_repaired,
    }
