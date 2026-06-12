from __future__ import annotations

import datetime as dt
import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.logging import get_logger


logger = get_logger(__name__)


def _extract_parent_ou_dn(dn: str | None) -> str | None:
    raw = str(dn or "").strip()
    if not raw or "," not in raw:
        return None
    parent = raw.split(",", 1)[1].strip()
    if not parent or not parent.lower().startswith("ou="):
        return None
    return parent


def _iter_ou_ancestor_dns(dn: str | None) -> list[str]:
    raw = str(dn or "").strip()
    if not raw or "," not in raw:
        return []

    current = raw.split(",", 1)[1].strip()
    if not current or not current.lower().startswith("ou="):
        return []

    out: list[str] = []
    seen: set[str] = set()
    while current and current.lower().startswith("ou="):
        key = current.lower()
        if key not in seen:
            out.append(current)
            seen.add(key)
        if "," not in current:
            break
        current = current.split(",", 1)[1].strip()
    return out


def _extract_ou_name(ou_dn: str) -> str:
    head = str(ou_dn or "").split(",", 1)[0].strip()
    if not head:
        return "OU"
    if "=" not in head:
        return head
    return head.split("=", 1)[1].strip() or "OU"


def _normalize_dn_for_match(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parts = [part.strip() for part in raw.split(",") if part is not None and str(part).strip()]
    return ",".join(parts)


def _coerce_mysql_datetime(value: Any) -> tuple[dt.datetime | None, bool]:
    """Return `(normalized_datetime, invalid)` for MySQL DATETIME columns.

    Accepted inputs:
    - Python `datetime`
    - ISO8601 (`...Z`, with/without microseconds, with timezone offsets)
    - LDAP generalized time (`YYYYmmddHHMMSS(.fff)Z`)

    Timezone-aware values are normalized to UTC and stored as naive datetimes
    because repository columns are `DATETIME` (timezone=False).
    """

    if value is None:
        return None, False

    if isinstance(value, dt.datetime):
        parsed = value
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(dt.timezone.utc).replace(tzinfo=None)
        return parsed, False

    raw = str(value).strip()
    if not raw:
        return None, False

    for fmt in (
        "%Y%m%d%H%M%S.%fZ",
        "%Y%m%d%H%M%S.0Z",
        "%Y%m%d%H%M%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
    ):
        try:
            return dt.datetime.strptime(raw, fmt), False
        except ValueError:
            continue

    try:
        cleaned = f"{raw[:-1]}+00:00" if raw.endswith("Z") else raw
        parsed = dt.datetime.fromisoformat(cleaned)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(dt.timezone.utc).replace(tzinfo=None)
        return parsed, False
    except Exception:
        return None, True


class DirectorySnapshotsRepo:
    def __init__(self, db: Session):
        self.db = db

    def create_run(
        self,
        *,
        identity_source_id: int,
        initiated_by: str | None,
        snapshot_source: str | None,
        correlation_id: str | None,
        summary_json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        source_id = int(identity_source_id)
        max_attempts = 5

        for _attempt in range(max_attempts):
            next_version_row = self.db.execute(
                text(
                    """
                    SELECT COALESCE(MAX(version), 0) + 1 AS next_version
                    FROM directory_snapshots
                    WHERE identity_source_id = :identity_source_id
                    """
                ),
                {"identity_source_id": source_id},
            ).mappings().first()
            next_version = int((next_version_row or {}).get("next_version") or 1)

            try:
                self.db.execute(
                    text(
                        """
                        INSERT INTO directory_snapshots (
                            identity_source_id,
                            version,
                            status,
                            snapshot_source,
                            initiated_by,
                            correlation_id,
                            summary_json,
                            started_at,
                            created_at,
                            updated_at
                        ) VALUES (
                            :identity_source_id,
                            :version,
                            'RUNNING',
                            :snapshot_source,
                            :initiated_by,
                            :correlation_id,
                            :summary_json,
                            NOW(6),
                            NOW(6),
                            NOW(6)
                        )
                        """
                    ),
                    {
                        "identity_source_id": source_id,
                        "version": next_version,
                        "snapshot_source": str(snapshot_source or "governance"),
                        "initiated_by": str(initiated_by or "").strip() or None,
                        "correlation_id": str(correlation_id or "").strip() or None,
                        "summary_json": json.dumps(summary_json or {}, ensure_ascii=False),
                    },
                )
                self.db.commit()
                return self.get_by_source_version(identity_source_id=source_id, version=next_version) or {}
            except IntegrityError:
                self.db.rollback()
                continue

        raise RuntimeError("Could not allocate unique snapshot version after retries")

    def list_runs(
        self,
        *,
        identity_source_id: int | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        rows = self.db.execute(
            text(
                """
                SELECT
                    id,
                    identity_source_id,
                    version,
                    status,
                    snapshot_source,
                    initiated_by,
                    correlation_id,
                    started_at,
                    finished_at,
                    activated_at,
                    archived_at,
                    summary_json,
                    error_message,
                    created_at,
                    updated_at
                FROM directory_snapshots
                WHERE (:identity_source_id IS NULL OR identity_source_id = :identity_source_id)
                  AND (:status IS NULL OR status = :status)
                ORDER BY id DESC
                LIMIT :limit
                """
            ),
            {
                "identity_source_id": int(identity_source_id) if identity_source_id is not None else None,
                "status": str(status or "").strip().upper() or None,
                "limit": max(1, min(int(limit or 50), 500)),
            },
        ).mappings().all()
        return [dict(r) for r in rows]

    def get(self, snapshot_id: int) -> dict[str, Any] | None:
        row = self.db.execute(
            text(
                """
                SELECT
                    id,
                    identity_source_id,
                    version,
                    status,
                    snapshot_source,
                    initiated_by,
                    correlation_id,
                    started_at,
                    finished_at,
                    activated_at,
                    archived_at,
                    summary_json,
                    error_message,
                    created_at,
                    updated_at
                FROM directory_snapshots
                WHERE id = :id
                LIMIT 1
                """
            ),
            {"id": int(snapshot_id)},
        ).mappings().first()
        return dict(row) if row else None

    def get_by_source_version(self, *, identity_source_id: int, version: int) -> dict[str, Any] | None:
        row = self.db.execute(
            text(
                """
                SELECT
                    id,
                    identity_source_id,
                    version,
                    status,
                    snapshot_source,
                    initiated_by,
                    correlation_id,
                    started_at,
                    finished_at,
                    activated_at,
                    archived_at,
                    summary_json,
                    error_message,
                    created_at,
                    updated_at
                FROM directory_snapshots
                WHERE identity_source_id = :identity_source_id
                  AND version = :version
                LIMIT 1
                """
            ),
            {
                "identity_source_id": int(identity_source_id),
                "version": int(version),
            },
        ).mappings().first()
        return dict(row) if row else None

    def get_latest_active(self, *, identity_source_id: int) -> dict[str, Any] | None:
        row = self.db.execute(
            text(
                """
                SELECT
                    id,
                    identity_source_id,
                    version,
                    status,
                    snapshot_source,
                    initiated_by,
                    correlation_id,
                    started_at,
                    finished_at,
                    activated_at,
                    archived_at,
                    summary_json,
                    error_message,
                    created_at,
                    updated_at
                FROM directory_snapshots
                WHERE identity_source_id = :identity_source_id
                  AND status = 'ACTIVE'
                ORDER BY version DESC, id DESC
                LIMIT 1
                """
            ),
            {"identity_source_id": int(identity_source_id)},
        ).mappings().first()
        return dict(row) if row else None

    def clone_from_snapshot(self, *, from_snapshot_id: int, to_snapshot_id: int) -> dict[str, int]:
        old_sid = int(from_snapshot_id)
        new_sid = int(to_snapshot_id)
        target = self.get(new_sid)
        target_version = int((target or {}).get("version") or 1)
        self.db.execute(
            text(
                """
                INSERT INTO directory_snapshot_users (
                    snapshot_id,
                    identity_source_id,
                    external_id,
                    object_guid,
                    object_sid,
                    upn,
                    dn,
                    when_changed,
                    usn_changed,
                    username,
                    display_name,
                    email,
                    source,
                    snapshot_version,
                    is_active,
                    created_at,
                    updated_at
                )
                SELECT
                    :to_snapshot_id,
                    identity_source_id,
                    external_id,
                    object_guid,
                    object_sid,
                    upn,
                    dn,
                    when_changed,
                    usn_changed,
                    username,
                    display_name,
                    email,
                    source,
                    :target_version,
                    is_active,
                    NOW(6),
                    NOW(6)
                FROM directory_snapshot_users
                WHERE snapshot_id = :from_snapshot_id
                """
            ),
            {
                "from_snapshot_id": old_sid,
                "to_snapshot_id": new_sid,
                "target_version": target_version,
            },
        )

        self.db.execute(
            text(
                """
                INSERT INTO directory_snapshot_groups (
                    snapshot_id,
                    identity_source_id,
                    external_id,
                    dn,
                    when_changed,
                    usn_changed,
                    name,
                    code,
                    description,
                    snapshot_version,
                    is_active,
                    created_at,
                    updated_at
                )
                SELECT
                    :to_snapshot_id,
                    identity_source_id,
                    external_id,
                    dn,
                    when_changed,
                    usn_changed,
                    name,
                    code,
                    description,
                    :target_version,
                    is_active,
                    NOW(6),
                    NOW(6)
                FROM directory_snapshot_groups
                WHERE snapshot_id = :from_snapshot_id
                """
            ),
            {
                "from_snapshot_id": old_sid,
                "to_snapshot_id": new_sid,
                "target_version": target_version,
            },
        )

        self.db.execute(
            text(
                """
                INSERT INTO directory_snapshot_memberships (
                    snapshot_id,
                    identity_source_id,
                    group_external_id,
                    member_external_id,
                    member_type,
                    created_at,
                    updated_at
                )
                SELECT
                    :to_snapshot_id,
                    identity_source_id,
                    group_external_id,
                    member_external_id,
                    member_type,
                    NOW(6),
                    NOW(6)
                FROM directory_snapshot_memberships
                WHERE snapshot_id = :from_snapshot_id
                """
            ),
            {"from_snapshot_id": old_sid, "to_snapshot_id": new_sid},
        )

        self.db.commit()
        counts = self.db.execute(
            text(
                """
                SELECT
                    (SELECT COUNT(*) FROM directory_snapshot_users WHERE snapshot_id = :snapshot_id) AS users,
                    (SELECT COUNT(*) FROM directory_snapshot_groups WHERE snapshot_id = :snapshot_id) AS groups,
                    (SELECT COUNT(*) FROM directory_snapshot_memberships WHERE snapshot_id = :snapshot_id) AS memberships
                """
            ),
            {"snapshot_id": new_sid},
        ).mappings().first() or {}
        return {
            "users": int(counts.get("users") or 0),
            "groups": int(counts.get("groups") or 0),
            "memberships": int(counts.get("memberships") or 0),
        }

    def patch_status(
        self,
        *,
        snapshot_id: int,
        status: str,
        summary_json: dict | None,
        error_message: str | None,
    ) -> dict[str, Any] | None:
        next_status = str(status or "").strip().upper()
        if not next_status:
            return self.get(snapshot_id)

        finish_states = {"SUCCEEDED", "FAILED", "ACTIVE", "ARCHIVED"}
        self.db.execute(
            text(
                """
                UPDATE directory_snapshots
                SET status = :status,
                    summary_json = :summary_json,
                    error_message = :error_message,
                    started_at = CASE
                        WHEN started_at IS NULL AND :status = 'RUNNING' THEN NOW(6)
                        ELSE started_at
                    END,
                    finished_at = CASE
                        WHEN :status IN ('SUCCEEDED','FAILED','ACTIVE','ARCHIVED') THEN COALESCE(finished_at, NOW(6))
                        ELSE finished_at
                    END,
                    updated_at = NOW(6)
                WHERE id = :id
                """
            ),
            {
                "id": int(snapshot_id),
                "status": next_status,
                "summary_json": json.dumps(summary_json or {}, ensure_ascii=False),
                "error_message": str(error_message or "").strip() or None,
            },
        )
        if next_status in finish_states and next_status != "ACTIVE":
            self.db.execute(
                text(
                    """
                    UPDATE directory_snapshots
                    SET finished_at = COALESCE(finished_at, NOW(6))
                    WHERE id = :id
                    """
                ),
                {"id": int(snapshot_id)},
            )
        self.db.commit()
        return self.get(snapshot_id)

    def bulk_upsert(
        self,
        *,
        snapshot_id: int,
        users: list[dict[str, Any]],
        groups: list[dict[str, Any]],
        memberships: list[dict[str, Any]],
    ) -> dict[str, Any]:
        snapshot = self.get(snapshot_id)
        if not snapshot:
            return {"snapshot_id": int(snapshot_id), "users": 0, "groups": 0, "memberships": 0}

        source_id = int(snapshot["identity_source_id"])
        version = int(snapshot["version"])

        if users:
            user_rows: list[dict[str, Any]] = []
            invalid_users_when_changed = 0
            for item in users:
                external_id = str(item.get("external_id") or "").strip()
                if not external_id:
                    continue

                when_changed, invalid_when_changed = _coerce_mysql_datetime(item.get("when_changed"))
                if invalid_when_changed:
                    invalid_users_when_changed += 1

                user_rows.append(
                    {
                        "snapshot_id": int(snapshot_id),
                        "identity_source_id": source_id,
                        "external_id": external_id,
                        "object_guid": str(item.get("object_guid") or "").strip() or None,
                        "object_sid": str(item.get("object_sid") or "").strip() or None,
                        "upn": str(item.get("upn") or "").strip() or None,
                        "dn": str(item.get("dn") or "").strip() or None,
                        "when_changed": when_changed,
                        "usn_changed": int(item.get("usn_changed")) if item.get("usn_changed") is not None else None,
                        "username": str(item.get("username") or "").strip() or None,
                        "display_name": str(item.get("display_name") or "").strip() or None,
                        "email": str(item.get("email") or "").strip() or None,
                        "source": str(item.get("source") or "snapshot").strip() or "snapshot",
                        "snapshot_version": version,
                        "is_active": 1 if bool(item.get("is_active", True)) else 0,
                    }
                )

            if invalid_users_when_changed:
                logger.warning(
                    "directory_snapshot.bulk_upsert normalized invalid users.when_changed to NULL",
                    extra={
                        "snapshot_id": int(snapshot_id),
                        "invalid_when_changed_count": int(invalid_users_when_changed),
                    },
                )

            if user_rows:
                self.db.execute(
                    text(
                        """
                        INSERT INTO directory_snapshot_users (
                            snapshot_id,
                            identity_source_id,
                            external_id,
                            object_guid,
                            object_sid,
                            upn,
                            dn,
                            when_changed,
                            usn_changed,
                            username,
                            display_name,
                            email,
                            source,
                            snapshot_version,
                            is_active,
                            created_at,
                            updated_at
                        ) VALUES (
                            :snapshot_id,
                            :identity_source_id,
                            :external_id,
                            :object_guid,
                            :object_sid,
                            :upn,
                            :dn,
                            :when_changed,
                            :usn_changed,
                            :username,
                            :display_name,
                            :email,
                            :source,
                            :snapshot_version,
                            :is_active,
                            NOW(6),
                            NOW(6)
                        )
                        ON DUPLICATE KEY UPDATE
                            object_guid = VALUES(object_guid),
                            object_sid = VALUES(object_sid),
                            upn = VALUES(upn),
                            dn = VALUES(dn),
                            when_changed = VALUES(when_changed),
                            usn_changed = VALUES(usn_changed),
                            username = VALUES(username),
                            display_name = VALUES(display_name),
                            email = VALUES(email),
                            source = VALUES(source),
                            snapshot_version = VALUES(snapshot_version),
                            is_active = VALUES(is_active),
                            updated_at = NOW(6)
                        """
                    ),
                    user_rows,
                )

        if groups:
            group_rows: list[dict[str, Any]] = []
            invalid_groups_when_changed = 0
            for item in groups:
                external_id = str(item.get("external_id") or "").strip()
                if not external_id:
                    continue

                when_changed, invalid_when_changed = _coerce_mysql_datetime(item.get("when_changed"))
                if invalid_when_changed:
                    invalid_groups_when_changed += 1

                group_rows.append(
                    {
                        "snapshot_id": int(snapshot_id),
                        "identity_source_id": source_id,
                        "external_id": external_id,
                        "dn": str(item.get("dn") or "").strip() or None,
                        "when_changed": when_changed,
                        "usn_changed": int(item.get("usn_changed")) if item.get("usn_changed") is not None else None,
                        "name": str(item.get("name") or "").strip() or None,
                        "code": str(item.get("code") or "").strip() or None,
                        "description": str(item.get("description") or "").strip() or None,
                        "snapshot_version": version,
                        "is_active": 1 if bool(item.get("is_active", True)) else 0,
                    }
                )

            if invalid_groups_when_changed:
                logger.warning(
                    "directory_snapshot.bulk_upsert normalized invalid groups.when_changed to NULL",
                    extra={
                        "snapshot_id": int(snapshot_id),
                        "invalid_when_changed_count": int(invalid_groups_when_changed),
                    },
                )

            if group_rows:
                self.db.execute(
                    text(
                        """
                        INSERT INTO directory_snapshot_groups (
                            snapshot_id,
                            identity_source_id,
                            external_id,
                            dn,
                            when_changed,
                            usn_changed,
                            name,
                            code,
                            description,
                            snapshot_version,
                            is_active,
                            created_at,
                            updated_at
                        ) VALUES (
                            :snapshot_id,
                            :identity_source_id,
                            :external_id,
                            :dn,
                            :when_changed,
                            :usn_changed,
                            :name,
                            :code,
                            :description,
                            :snapshot_version,
                            :is_active,
                            NOW(6),
                            NOW(6)
                        )
                        ON DUPLICATE KEY UPDATE
                            dn = VALUES(dn),
                            when_changed = VALUES(when_changed),
                            usn_changed = VALUES(usn_changed),
                            name = VALUES(name),
                            code = VALUES(code),
                            description = VALUES(description),
                            snapshot_version = VALUES(snapshot_version),
                            is_active = VALUES(is_active),
                            updated_at = NOW(6)
                        """
                    ),
                    group_rows,
                )

        if memberships:
            touched_groups = {
                str(item.get("group_external_id") or "").strip()
                for item in memberships
                if str(item.get("group_external_id") or "").strip()
            }
            if touched_groups:
                self.db.execute(
                    text(
                        """
                        DELETE FROM directory_snapshot_memberships
                        WHERE snapshot_id = :snapshot_id
                          AND group_external_id = :group_external_id
                        """
                    ),
                    [
                        {
                            "snapshot_id": int(snapshot_id),
                            "group_external_id": gid,
                        }
                        for gid in sorted(touched_groups)
                    ],
                )

            self.db.execute(
                text(
                    """
                    INSERT INTO directory_snapshot_memberships (
                        snapshot_id,
                        identity_source_id,
                        group_external_id,
                        member_external_id,
                        member_type,
                        created_at,
                        updated_at
                    ) VALUES (
                        :snapshot_id,
                        :identity_source_id,
                        :group_external_id,
                        :member_external_id,
                        :member_type,
                        NOW(6),
                        NOW(6)
                    )
                    ON DUPLICATE KEY UPDATE
                        member_type = VALUES(member_type),
                        updated_at = NOW(6)
                    """
                ),
                [
                    {
                        "snapshot_id": int(snapshot_id),
                        "identity_source_id": source_id,
                        "group_external_id": str(item.get("group_external_id") or "").strip(),
                        "member_external_id": str(item.get("member_external_id") or "").strip(),
                        "member_type": str(item.get("member_type") or "user").strip().lower() or "user",
                    }
                    for item in memberships
                    if str(item.get("group_external_id") or "").strip() and str(item.get("member_external_id") or "").strip()
                ],
            )

        self.db.commit()

        count_row = self.db.execute(
            text(
                """
                SELECT
                    (SELECT COUNT(*) FROM directory_snapshot_users WHERE snapshot_id = :snapshot_id) AS users,
                    (SELECT COUNT(*) FROM directory_snapshot_groups WHERE snapshot_id = :snapshot_id) AS groups,
                    (SELECT COUNT(*) FROM directory_snapshot_memberships WHERE snapshot_id = :snapshot_id) AS memberships
                """
            ),
            {"snapshot_id": int(snapshot_id)},
        ).mappings().first() or {}

        return {
            "snapshot_id": int(snapshot_id),
            "users": int(count_row.get("users") or 0),
            "groups": int(count_row.get("groups") or 0),
            "memberships": int(count_row.get("memberships") or 0),
        }

    def activate(self, *, snapshot_id: int, activated_by: str | None = None) -> dict[str, Any] | None:
        snapshot = self.get(snapshot_id)
        if not snapshot:
            return None

        sid = int(snapshot_id)
        source_id = int(snapshot["identity_source_id"])
        version = int(snapshot["version"])
        source_label = str(snapshot.get("snapshot_source") or "snapshot")

        self.db.execute(
            text(
                """
                UPDATE directory_snapshots
                SET status = 'ARCHIVED',
                    archived_at = COALESCE(archived_at, NOW(6)),
                    updated_at = NOW(6)
                WHERE identity_source_id = :identity_source_id
                  AND id <> :snapshot_id
                  AND status = 'ACTIVE'
                """
            ),
            {
                "identity_source_id": source_id,
                "snapshot_id": sid,
            },
        )

        self.db.execute(
            text(
                """
                UPDATE directory_snapshots
                SET status = 'ACTIVE',
                    initiated_by = COALESCE(:activated_by, initiated_by),
                    activated_at = COALESCE(activated_at, NOW(6)),
                    finished_at = COALESCE(finished_at, NOW(6)),
                    updated_at = NOW(6)
                WHERE id = :snapshot_id
                """
            ),
            {
                "snapshot_id": sid,
                "activated_by": str(activated_by or "").strip() or None,
            },
        )

        self.db.execute(
            text(
                """
                INSERT INTO directory_groups (
                    identity_source_id,
                    external_id,
                    dn,
                    when_changed,
                    usn_changed,
                    name,
                    code,
                    description,
                    snapshot_version,
                    snapshot_source,
                    snapshot_hash,
                    last_snapshot_at,
                    captured_at,
                    created_at,
                    updated_at,
                    deleted_at
                )
                SELECT
                    sg.identity_source_id,
                    sg.external_id,
                    sg.dn,
                    sg.when_changed,
                    sg.usn_changed,
                    COALESCE(NULLIF(TRIM(sg.name), ''), NULLIF(TRIM(sg.code), ''), sg.external_id) AS name,
                    sg.code,
                    sg.description,
                    :version AS snapshot_version,
                    :snapshot_source AS snapshot_source,
                    NULL AS snapshot_hash,
                    NOW(6) AS last_snapshot_at,
                    NOW(6) AS captured_at,
                    NOW(6) AS created_at,
                    NOW(6) AS updated_at,
                    NULL AS deleted_at
                FROM directory_snapshot_groups sg
                WHERE sg.snapshot_id = :snapshot_id
                ON DUPLICATE KEY UPDATE
                    dn = VALUES(dn),
                    when_changed = VALUES(when_changed),
                    usn_changed = VALUES(usn_changed),
                    name = VALUES(name),
                    code = VALUES(code),
                    description = VALUES(description),
                    snapshot_version = VALUES(snapshot_version),
                    snapshot_source = VALUES(snapshot_source),
                    last_snapshot_at = VALUES(last_snapshot_at),
                    updated_at = NOW(6),
                    deleted_at = NULL
                """
            ),
            {
                "snapshot_id": sid,
                "version": version,
                "snapshot_source": source_label,
            },
        )

        self.db.execute(
            text(
                """
                INSERT INTO directory_users (
                    identity_source_id,
                    external_id,
                    object_guid,
                    object_sid,
                    upn,
                    dn,
                    when_changed,
                    usn_changed,
                    username,
                    display_name,
                    email,
                    snapshot_version,
                    snapshot_source,
                    snapshot_hash,
                    last_snapshot_at,
                    captured_at,
                    created_at,
                    updated_at,
                    ou_id
                )
                SELECT
                    su.identity_source_id,
                    su.external_id,
                    su.object_guid,
                    su.object_sid,
                    su.upn,
                    su.dn,
                    su.when_changed,
                    su.usn_changed,
                    su.username,
                    COALESCE(NULLIF(TRIM(su.display_name), ''), NULLIF(TRIM(su.username), ''), su.external_id) AS display_name,
                    su.email,
                    :version AS snapshot_version,
                    :snapshot_source AS snapshot_source,
                    NULL AS snapshot_hash,
                    NOW(6) AS last_snapshot_at,
                    NOW(6) AS captured_at,
                    NOW(6) AS created_at,
                    NOW(6) AS updated_at,
                    NULL AS ou_id
                FROM directory_snapshot_users su
                WHERE su.snapshot_id = :snapshot_id
                    ON DUPLICATE KEY UPDATE
                        object_guid = VALUES(object_guid),
                        object_sid = VALUES(object_sid),
                        upn = VALUES(upn),
                        dn = VALUES(dn),
                        when_changed = VALUES(when_changed),
                        usn_changed = VALUES(usn_changed),
                        username = VALUES(username),
                        display_name = VALUES(display_name),
                        email = VALUES(email),
                    snapshot_version = VALUES(snapshot_version),
                    snapshot_source = VALUES(snapshot_source),
                    last_snapshot_at = VALUES(last_snapshot_at),
                    updated_at = NOW(6)
                """
            ),
            {
                "snapshot_id": sid,
                "version": version,
                "snapshot_source": source_label,
            },
        )

        # Project discovered OUs (best effort) from users/groups DNs.
        snapshot_dns_rows = self.db.execute(
            text(
                """
                SELECT dn
                FROM directory_snapshot_users
                WHERE snapshot_id = :snapshot_id
                  AND dn IS NOT NULL
                UNION
                SELECT dn
                FROM directory_snapshot_groups
                WHERE snapshot_id = :snapshot_id
                  AND dn IS NOT NULL
                """
            ),
            {"snapshot_id": sid},
        ).mappings().all()

        ou_rows_by_key: dict[str, dict[str, Any]] = {}
        for row in snapshot_dns_rows:
            for ou_dn in _iter_ou_ancestor_dns(row.get("dn")):
                key = ou_dn.lower()
                if key in ou_rows_by_key:
                    continue
                ou_rows_by_key[key] = {
                    "identity_source_id": source_id,
                    "external_id": ou_dn,
                    "dn": ou_dn,
                    "name": _extract_ou_name(ou_dn),
                }

        if ou_rows_by_key:
            self.db.execute(
                text(
                    """
                    INSERT INTO directory_ous (
                        identity_source_id,
                        external_id,
                        dn,
                        name,
                        captured_at,
                        created_at,
                        updated_at
                    ) VALUES (
                        :identity_source_id,
                        :external_id,
                        :dn,
                        :name,
                        NOW(6),
                        NOW(6),
                        NOW(6)
                    )
                    ON DUPLICATE KEY UPDATE
                        dn = VALUES(dn),
                        name = VALUES(name),
                        captured_at = NOW(6),
                        updated_at = NOW(6)
                    """
                ),
                list(ou_rows_by_key.values()),
            )

        # Attach projected users to their parent OU when resolvable.
        self.db.execute(
            text(
                """
                UPDATE directory_users du
                LEFT JOIN directory_ous dou
                  ON dou.identity_source_id = du.identity_source_id
                 AND LOWER(dou.external_id) = LOWER(TRIM(SUBSTRING(du.dn, LOCATE(',', du.dn) + 1)))
                SET du.ou_id = CASE
                    WHEN du.dn IS NULL
                      OR LOCATE(',', du.dn) = 0
                      OR LOWER(TRIM(SUBSTRING(du.dn, LOCATE(',', du.dn) + 1))) NOT LIKE 'ou=%'
                        THEN NULL
                    ELSE dou.id
                END,
                    du.updated_at = NOW(6)
                WHERE du.identity_source_id = :identity_source_id
                """
            ),
            {"identity_source_id": source_id},
        )

        self.db.execute(
            text(
                """
                UPDATE identity_sources
                SET
                    last_snapshot_at = NOW(6),
                    last_snapshot_version = :snapshot_version,
                    snapshot_mode = COALESCE(
                        NULLIF((
                            SELECT JSON_UNQUOTE(JSON_EXTRACT(ds.summary_json, '$.mode'))
                            FROM directory_snapshots ds
                            WHERE ds.id = :snapshot_id
                            LIMIT 1
                        ), ''),
                        snapshot_mode,
                        'full'
                    ),
                    updated_at = NOW(6)
                WHERE id = :identity_source_id
                """
            ),
            {
                "identity_source_id": source_id,
                "snapshot_version": version,
                "snapshot_id": sid,
            },
        )

        self.db.execute(
            text(
                """
                UPDATE identity_sources i
                JOIN (
                    SELECT COALESCE(MAX(usn_changed), NULL) AS max_usn
                    FROM (
                        SELECT su.usn_changed
                        FROM directory_snapshot_users su
                        WHERE su.snapshot_id = :snapshot_id
                          AND su.usn_changed IS NOT NULL
                        UNION ALL
                        SELECT sg.usn_changed
                        FROM directory_snapshot_groups sg
                        WHERE sg.snapshot_id = :snapshot_id
                          AND sg.usn_changed IS NOT NULL
                    ) x
                ) m ON 1 = 1
                SET i.last_usn_changed = COALESCE(m.max_usn, i.last_usn_changed),
                    i.updated_at = NOW(6)
                WHERE i.id = :identity_source_id
                """
            ),
            {
                "snapshot_id": sid,
                "identity_source_id": source_id,
            },
        )

        self.db.execute(
            text(
                """
                DELETE dgm
                FROM directory_group_members dgm
                JOIN directory_groups dg ON dg.id = dgm.group_id
                WHERE dg.identity_source_id = :identity_source_id
                """
            ),
            {"identity_source_id": source_id},
        )

        self.db.execute(
            text(
                """
                INSERT IGNORE INTO directory_group_members (group_id, directory_user_id, created_at, updated_at, deleted_at)
                SELECT
                    dg.id,
                    du.id,
                    NOW(6),
                    NOW(6),
                    NULL
                FROM directory_snapshot_memberships sm
                JOIN directory_groups dg
                  ON dg.identity_source_id = sm.identity_source_id
                 AND dg.external_id = sm.group_external_id
                JOIN directory_users du
                  ON du.identity_source_id = sm.identity_source_id
                 AND du.external_id = sm.member_external_id
                WHERE sm.snapshot_id = :snapshot_id
                """
            ),
            {"snapshot_id": sid},
        )

        self.db.commit()
        return self.get(sid)

    def search(
        self,
        *,
        snapshot_id: int,
        query: str | None,
        principal_type: str,
        base_dn: str | None,
        search_scope: str,
        limit: int,
        enabled_only: bool = False,
    ) -> list[dict[str, Any]]:
        q = str(query or "").strip()
        like = f"%{q}%" if q else "%"
        ptype = str(principal_type or "all").strip().lower()
        scope = str(search_scope or "subtree").strip().lower()
        if scope not in {"subtree", "onelevel", "base"}:
            scope = "subtree"
        base = _normalize_dn_for_match(base_dn)
        base_like = f"%,{base}" if base else ""

        def _dn_norm_expr(column_expr: str) -> str:
            return (
                f"LOWER(REPLACE(REPLACE(TRIM(COALESCE({column_expr}, '')), ', ', ','), ' ,', ','))"
            )

        def _dn_clause(column: str) -> str:
            if not base:
                return "1=1"
            if scope == "base":
                return f"{_dn_norm_expr(column)} = LOWER(:base_dn)"
            if scope == "onelevel":
                parent_expr = f"SUBSTRING({column}, LOCATE(',', {column}) + 1)"
                return (
                    f"LOCATE(',', {column}) > 0 "
                    f"AND {_dn_norm_expr(parent_expr)} = LOWER(:base_dn)"
                )
            return (
                f"{_dn_norm_expr(column)} = LOWER(:base_dn) "
                f"OR {_dn_norm_expr(column)} LIKE LOWER(:base_like)"
            )

        lim = max(1, min(int(limit or 25), 200))
        users_enabled_clause = "AND is_active = 1" if bool(enabled_only) else ""

        out: list[dict[str, Any]] = []
        if ptype in {"all", "user"}:
            users = self.db.execute(
                text(
                    f"""
                    SELECT
                        'user' AS principal_type,
                        external_id,
                        COALESCE(NULLIF(TRIM(display_name), ''), NULLIF(TRIM(username), ''), external_id) AS display_name,
                        username,
                        email,
                        dn,
                        object_sid,
                        upn,
                        is_active
                    FROM directory_snapshot_users
                    WHERE snapshot_id = :snapshot_id
                      {users_enabled_clause}
                      AND ({_dn_clause('dn')})
                      AND (
                        :q = ''
                        OR external_id LIKE :like
                        OR username LIKE :like
                        OR display_name LIKE :like
                        OR email LIKE :like
                        OR dn LIKE :like
                        OR upn LIKE :like
                        OR object_sid LIKE :like
                      )
                    ORDER BY display_name, external_id
                    LIMIT :limit
                    """
                ),
                {
                    "snapshot_id": int(snapshot_id),
                    "q": q,
                    "like": like,
                    "base_dn": base or None,
                    "base_like": base_like or None,
                    "limit": lim,
                },
            ).mappings().all()
            out.extend(dict(r) for r in users)

        if ptype in {"all", "group"}:
            groups = self.db.execute(
                text(
                    f"""
                    SELECT
                        'group' AS principal_type,
                        external_id,
                        COALESCE(NULLIF(TRIM(name), ''), NULLIF(TRIM(code), ''), external_id) AS display_name,
                        code AS username,
                        NULL AS email,
                        dn,
                        NULL AS object_sid,
                        NULL AS upn
                    FROM directory_snapshot_groups
                    WHERE snapshot_id = :snapshot_id
                      AND ({_dn_clause('dn')})
                      AND (
                        :q = ''
                        OR external_id LIKE :like
                        OR name LIKE :like
                        OR code LIKE :like
                        OR dn LIKE :like
                      )
                    ORDER BY display_name, external_id
                    LIMIT :limit
                    """
                ),
                {
                    "snapshot_id": int(snapshot_id),
                    "q": q,
                    "like": like,
                    "base_dn": base or None,
                    "base_like": base_like or None,
                    "limit": lim,
                },
            ).mappings().all()
            out.extend(dict(r) for r in groups)

        if ptype in {"all", "ou"}:
            ous = self.db.execute(
                text(
                    f"""
                    SELECT
                        'ou' AS principal_type,
                        external_id,
                        COALESCE(NULLIF(TRIM(name), ''), external_id) AS display_name,
                        NULL AS username,
                        NULL AS email,
                        dn,
                        NULL AS object_sid,
                        NULL AS upn
                    FROM directory_ous
                    WHERE identity_source_id = (
                        SELECT identity_source_id
                        FROM directory_snapshots
                        WHERE id = :snapshot_id
                        LIMIT 1
                    )
                      AND ({_dn_clause('dn')})
                      AND (
                        :q = ''
                        OR external_id LIKE :like
                        OR name LIKE :like
                        OR dn LIKE :like
                      )
                    ORDER BY display_name, external_id
                    LIMIT :limit
                    """
                ),
                {
                    "snapshot_id": int(snapshot_id),
                    "q": q,
                    "like": like,
                    "base_dn": base or None,
                    "base_like": base_like or None,
                    "limit": lim,
                },
            ).mappings().all()
            out.extend(dict(r) for r in ous)

        if len(out) > lim:
            out = out[:lim]
        return out
