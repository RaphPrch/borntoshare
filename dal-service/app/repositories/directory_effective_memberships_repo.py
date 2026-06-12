from __future__ import annotations

import hashlib
from collections import deque
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


class DirectoryEffectiveMembershipsRepo:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _norm(value: Any) -> str:
        return str(value or "").strip().lower()

    def get_snapshot(self, snapshot_id: int) -> dict[str, Any] | None:
        row = self.db.execute(
            text(
                """
                SELECT id, identity_source_id, status, version
                FROM directory_snapshots
                WHERE id = :snapshot_id
                LIMIT 1
                """
            ),
            {"snapshot_id": int(snapshot_id)},
        ).mappings().first()
        return dict(row) if row else None

    def get_active_snapshot(self, identity_source_id: int) -> dict[str, Any] | None:
        row = self.db.execute(
            text(
                """
                SELECT id, identity_source_id, status, version
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

    def list_active_snapshots(self) -> list[dict[str, Any]]:
        rows = self.db.execute(
            text(
                """
                SELECT id, identity_source_id, status, version
                FROM directory_snapshots
                WHERE status = 'ACTIVE'
                ORDER BY identity_source_id ASC, version DESC, id DESC
                """
            )
        ).mappings().all()
        return [dict(r) for r in rows]

    def rebuild_for_identity_source(self, identity_source_id: int) -> dict[str, Any]:
        active = self.get_active_snapshot(identity_source_id)
        if not active:
            return {
                "identity_source_id": int(identity_source_id),
                "snapshot_id": None,
                "inserted": 0,
                "status": "no_active_snapshot",
            }
        return self.rebuild_for_snapshot(int(active["id"]))

    def rebuild_all_active(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for snap in self.list_active_snapshots():
            out.append(self.rebuild_for_snapshot(int(snap["id"])))
        return out

    def rebuild_for_snapshot(self, snapshot_id: int) -> dict[str, Any]:
        snapshot = self.get_snapshot(snapshot_id)
        if not snapshot:
            return {
                "snapshot_id": int(snapshot_id),
                "inserted": 0,
                "status": "snapshot_not_found",
            }

        sid = int(snapshot["id"])
        source_id = int(snapshot["identity_source_id"])

        snapshot_users_rows = self.db.execute(
            text(
                """
                SELECT external_id, dn, username, upn, email
                FROM directory_snapshot_users
                WHERE snapshot_id = :snapshot_id
                """
            ),
            {"snapshot_id": sid},
        ).mappings().all()

        snapshot_groups_rows = self.db.execute(
            text(
                """
                SELECT external_id, dn, name, code
                FROM directory_snapshot_groups
                WHERE snapshot_id = :snapshot_id
                """
            ),
            {"snapshot_id": sid},
        ).mappings().all()

        active_users_rows = self.db.execute(
            text(
                """
                SELECT id, external_id, dn, username, upn, email
                FROM directory_users
                WHERE identity_source_id = :identity_source_id
                """
            ),
            {"identity_source_id": source_id},
        ).mappings().all()

        active_groups_rows = self.db.execute(
            text(
                """
                SELECT id, external_id, dn, name, code
                FROM directory_groups
                WHERE identity_source_id = :identity_source_id
                """
            ),
            {"identity_source_id": source_id},
        ).mappings().all()

        memberships_rows = self.db.execute(
            text(
                """
                SELECT group_external_id, member_external_id, LOWER(COALESCE(member_type, 'user')) AS member_type
                FROM directory_snapshot_memberships
                WHERE snapshot_id = :snapshot_id
                """
            ),
            {"snapshot_id": sid},
        ).mappings().all()

        snapshot_group_alias_to_external: dict[str, str] = {}
        for row in snapshot_groups_rows:
            canonical = self._norm(row.get("external_id"))
            if not canonical:
                continue
            for field in ("external_id", "dn", "name", "code"):
                key = self._norm(row.get(field))
                if key and key not in snapshot_group_alias_to_external:
                    snapshot_group_alias_to_external[key] = canonical

        snapshot_user_alias_to_external: dict[str, str] = {}
        for row in snapshot_users_rows:
            canonical = self._norm(row.get("external_id"))
            if not canonical:
                continue
            for field in ("external_id", "dn", "username", "upn", "email"):
                key = self._norm(row.get(field))
                if key and key not in snapshot_user_alias_to_external:
                    snapshot_user_alias_to_external[key] = canonical

        group_lookup: dict[str, int] = {}
        group_ids: list[int] = []
        for row in active_groups_rows:
            gid = int(row["id"])
            group_ids.append(gid)
            for field in ("external_id", "dn", "name", "code"):
                key = self._norm(row.get(field))
                if key and key not in group_lookup:
                    group_lookup[key] = gid

        user_lookup: dict[str, int] = {}
        for row in active_users_rows:
            uid = int(row["id"])
            for field in ("external_id", "dn", "username", "upn", "email"):
                key = self._norm(row.get(field))
                if key and key not in user_lookup:
                    user_lookup[key] = uid

        direct_users: dict[int, set[int]] = {gid: set() for gid in group_ids}
        nested_groups: dict[int, set[int]] = {gid: set() for gid in group_ids}
        skipped = 0

        for row in memberships_rows:
            raw_group_key = self._norm(row.get("group_external_id"))
            canonical_group_key = snapshot_group_alias_to_external.get(raw_group_key, raw_group_key)
            group_id = group_lookup.get(canonical_group_key) or group_lookup.get(raw_group_key)
            if group_id is None:
                skipped += 1
                continue

            member_key = self._norm(row.get("member_external_id"))
            member_type = self._norm(row.get("member_type")) or "user"
            if member_type == "group":
                canonical_member_group = snapshot_group_alias_to_external.get(member_key, member_key)
                child_group_id = group_lookup.get(canonical_member_group) or group_lookup.get(member_key)
                if child_group_id is None:
                    skipped += 1
                    continue
                nested_groups[group_id].add(child_group_id)
                continue

            canonical_member_user = snapshot_user_alias_to_external.get(member_key, member_key)
            user_id = user_lookup.get(canonical_member_user) or user_lookup.get(member_key)
            if user_id is None:
                skipped += 1
                continue
            direct_users[group_id].add(user_id)

        by_pair: dict[tuple[int, int], dict[str, Any]] = {}

        for root_group_id in group_ids:
            queue: deque[tuple[int, int, tuple[int, ...]]] = deque()
            queue.append((root_group_id, 0, (root_group_id,)))

            while queue:
                current_group_id, depth, path = queue.popleft()

                for user_id in direct_users.get(current_group_id, set()):
                    pair = (user_id, root_group_id)
                    existing = by_pair.get(pair)
                    if existing and int(existing["depth"]) <= int(depth):
                        continue

                    path_repr = ">".join(str(v) for v in path)
                    path_hash = hashlib.sha256(
                        f"src:{source_id}|snap:{sid}|grp:{root_group_id}|usr:{user_id}|path:{path_repr}".encode("utf-8")
                    ).hexdigest()
                    by_pair[pair] = {
                        "identity_source_id": source_id,
                        "snapshot_id": sid,
                        "directory_user_id": user_id,
                        "directory_group_id": root_group_id,
                        "depth": int(depth),
                        "path_hash": path_hash,
                        "resolution_type": "direct" if int(depth) == 0 else "nested",
                    }

                for child_group_id in nested_groups.get(current_group_id, set()):
                    if child_group_id in path:
                        continue
                    queue.append((child_group_id, int(depth) + 1, path + (child_group_id,)))

        rows_to_insert = list(by_pair.values())

        self.db.execute(
            text(
                """
                DELETE FROM directory_effective_memberships
                WHERE identity_source_id = :identity_source_id
                """
            ),
            {"identity_source_id": source_id},
        )

        if rows_to_insert:
            self.db.execute(
                text(
                    """
                    INSERT INTO directory_effective_memberships (
                        identity_source_id,
                        snapshot_id,
                        directory_user_id,
                        directory_group_id,
                        depth,
                        path_hash,
                        resolution_type,
                        created_at,
                        updated_at
                    ) VALUES (
                        :identity_source_id,
                        :snapshot_id,
                        :directory_user_id,
                        :directory_group_id,
                        :depth,
                        :path_hash,
                        :resolution_type,
                        NOW(6),
                        NOW(6)
                    )
                    """
                ),
                rows_to_insert,
            )

        self.db.commit()

        return {
            "snapshot_id": sid,
            "identity_source_id": source_id,
            "inserted": len(rows_to_insert),
            "groups": len(group_ids),
            "users": len(snapshot_users_rows),
            "memberships": len(memberships_rows),
            "skipped_memberships": skipped,
            "status": "ok",
        }
