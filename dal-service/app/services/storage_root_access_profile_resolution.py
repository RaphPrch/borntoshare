from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.repositories.storage_root_access_profiles_repo import StorageRootAccessProfilesRepo
from app.services.storage_root_binding_materialization_service import repair_missing_root_bindings


ResolutionStatus = Literal[
    "resolved",
    "missing_binding",
    "ambiguous_binding",
    "invalid_permission",
    "unsupported_target_type",
]


@dataclass(frozen=True)
class StorageRootAccessProfileResolution:
    status: ResolutionStatus
    code: str | None
    message: str
    hint: str | None
    storage_root_id: int | None
    requested_permission: str | None
    candidates_count: int
    storage_root_access_profile_id: int | None = None
    access_profile_id: int | None = None
    access_profile_code: str | None = None
    group_ref: str | None = None
    group_name: str | None = None
    effective_group_ou_dn: str | None = None
    identity_source_id: int | None = None
    profile_status: str | None = None
    group_external_id: str | None = None
    candidates: list[dict[str, Any]] | None = None
    repair_attempted: bool = False
    repair_result: str | None = None

    def to_error_detail(self, *, item_id: int | None = None) -> dict[str, Any]:
        payload = {
            "item_id": int(item_id or 0) or None,
            "code": self.code,
            "message": self.message,
            "hint": self.hint,
            "storage_root_id": self.storage_root_id,
            "requested_permission": self.requested_permission,
            "candidates_count": int(self.candidates_count),
            "repair_attempted": bool(self.repair_attempted),
            "repair_result": self.repair_result,
        }
        return payload


def normalize_requested_permission(permission: str | None) -> Literal["READ", "WRITE"] | None:
    raw = str(permission or "").strip().lower()
    if raw in {
        "read",
        "read_ntfs",
        "read-only",
        "read_only",
        "audit",
    }:
        return "READ"
    if raw in {
        "write",
        "write_ntfs",
        "modify",
        "read_write",
        "read-write",
        "contribution",
        "change",
        "owner",
        "admin",
        "full",
        "fullcontrol",
        "full_control",
        "rw",
        "rwx",
    }:
        return "WRITE"
    return None


def _looks_like_legacy_duplicated_permission_group_name(
    *,
    group_ref: str | None,
    requested_permission: str | None,
) -> bool:
    normalized = str(group_ref or "").strip().upper()
    if not normalized:
        return False

    canonical_permission = str(requested_permission or "").strip().upper()
    duplicated_suffixes = {
        "READ": ("_READ_READ", "_RX_RX"),
        "WRITE": ("_WRITE_WRITE", "_RW_RW"),
    }
    suffixes = duplicated_suffixes.get(canonical_permission)
    if not suffixes:
        return False

    return any(normalized.endswith(sfx) for sfx in suffixes)


def build_resolution_error(
    *,
    status: ResolutionStatus,
    storage_root_id: int | None,
    requested_permission: str | None,
    candidates_count: int = 0,
    candidates: list[dict[str, Any]] | None = None,
    repair_attempted: bool = False,
    repair_result: str | None = None,
) -> StorageRootAccessProfileResolution:
    permission = str(requested_permission or "").strip().upper() or None

    if status == "invalid_permission":
        return StorageRootAccessProfileResolution(
            status="invalid_permission",
            code="INVALID_REQUEST_PERMISSION",
            message=f"Requested permission '{str(requested_permission or '').strip()}' is not supported.",
            hint="Use READ or WRITE permission values.",
            storage_root_id=int(storage_root_id) if storage_root_id else None,
            requested_permission=permission,
            candidates_count=0,
            repair_attempted=repair_attempted,
            repair_result=repair_result,
        )

    if status == "unsupported_target_type":
        return StorageRootAccessProfileResolution(
            status="unsupported_target_type",
            code="UNSUPPORTED_TARGET_TYPE",
            message="Only storage_root target type is supported for approval provisioning.",
            hint="Submit a request targeting a storage_root.",
            storage_root_id=int(storage_root_id) if storage_root_id else None,
            requested_permission=permission,
            candidates_count=0,
            repair_attempted=repair_attempted,
            repair_result=repair_result,
        )

    if status == "ambiguous_binding":
        return StorageRootAccessProfileResolution(
            status="ambiguous_binding",
            code="STORAGE_ROOT_ACCESS_PROFILE_AMBIGUOUS",
            message=(
                "More than one active storage-root access profile binding matches "
                f"permission {permission or 'UNKNOWN'}."
            ),
            hint=(
                "Keep only one active binding per storage root and permission "
                "(READ/WRITE)."
            ),
            storage_root_id=int(storage_root_id) if storage_root_id else None,
            requested_permission=permission,
            candidates_count=int(candidates_count),
            candidates=list(candidates or []),
            repair_attempted=repair_attempted,
            repair_result=repair_result,
        )

    return StorageRootAccessProfileResolution(
        status="missing_binding",
        code="STORAGE_ROOT_ACCESS_PROFILE_MISSING",
        message=(
            "No active storage-root access profile is linked to permission "
            f"{permission or 'UNKNOWN'}."
        ),
        hint=(
            f"Attach a {permission or 'READ/WRITE'} access profile to this storage root "
            "before approval."
        ),
        storage_root_id=int(storage_root_id) if storage_root_id else None,
        requested_permission=permission,
        candidates_count=0,
        repair_attempted=repair_attempted,
        repair_result=repair_result,
    )


def resolve_storage_root_access_profile(
    *,
    db: Session,
    storage_root_id: int,
    requested_permission: str | None,
    target_type: str = "storage_root",
) -> StorageRootAccessProfileResolution:
    normalized_target = str(target_type or "").strip().lower()
    if normalized_target != "storage_root":
        return build_resolution_error(
            status="unsupported_target_type",
            storage_root_id=storage_root_id,
            requested_permission=requested_permission,
        )

    root_id = int(storage_root_id or 0)
    canonical_permission = normalize_requested_permission(requested_permission)
    if root_id <= 0 or canonical_permission is None:
        return build_resolution_error(
            status="invalid_permission",
            storage_root_id=root_id if root_id > 0 else None,
            requested_permission=requested_permission,
        )

    repo = StorageRootAccessProfilesRepo(db)

    def _query_candidates() -> list[dict[str, Any]]:
        return repo.list_active_storage_root_profile_candidates(
            storage_root_id=root_id,
            canonical_permission=canonical_permission,
        )

    repair_attempted = False
    repair_result: str | None = None
    candidates = _query_candidates()

    if len(candidates) == 0:
        repair_attempted = True
        try:
            report = repair_missing_root_bindings(
                db,
                storage_root_id=int(root_id),
                commit=True,
            )
            repair_result = (
                "repaired" if bool((report.to_dict() or {}).get("repaired")) else "noop"
            )
        except Exception:
            repair_result = "error"
        candidates = _query_candidates()

    if len(candidates) == 1:
        winner = dict(candidates[0])
        if _looks_like_legacy_duplicated_permission_group_name(
            group_ref=winner.get("group_ref"),
            requested_permission=canonical_permission,
        ):
            repair_attempted = True
            try:
                report = repair_missing_root_bindings(
                    db,
                    storage_root_id=int(root_id),
                    commit=True,
                )
                repair_result = (
                    "repaired" if bool((report.to_dict() or {}).get("repaired")) else "noop"
                )
            except Exception:
                repair_result = "error"
            candidates = _query_candidates()

    if len(candidates) == 0:
        return build_resolution_error(
            status="missing_binding",
            storage_root_id=root_id,
            requested_permission=canonical_permission,
            repair_attempted=repair_attempted,
            repair_result=repair_result,
        )

    if len(candidates) > 1:
        return build_resolution_error(
            status="ambiguous_binding",
            storage_root_id=root_id,
            requested_permission=canonical_permission,
            candidates_count=len(candidates),
            candidates=candidates,
            repair_attempted=repair_attempted,
            repair_result=repair_result,
        )

    winner = dict(candidates[0])
    return StorageRootAccessProfileResolution(
        status="resolved",
        code=None,
        message="Binding resolved",
        hint=None,
        storage_root_id=root_id,
        requested_permission=canonical_permission,
        candidates_count=1,
        storage_root_access_profile_id=int(winner.get("storage_root_access_profile_id") or 0) or None,
        access_profile_id=int(winner.get("access_profile_id") or 0) or None,
        access_profile_code=str(winner.get("access_profile_code") or "").strip() or None,
        group_ref=str(winner.get("group_ref") or "").strip() or None,
        group_name=str(winner.get("group_name") or "").strip() or None,
        effective_group_ou_dn=str(winner.get("effective_group_ou_dn") or "").strip() or None,
        identity_source_id=int(winner.get("identity_source_id") or 0) or None,
        profile_status=str(winner.get("profile_status") or "").strip().upper() or None,
        group_external_id=str(winner.get("group_external_id") or "").strip() or None,
        candidates=candidates,
        repair_attempted=repair_attempted,
        repair_result=repair_result,
    )
