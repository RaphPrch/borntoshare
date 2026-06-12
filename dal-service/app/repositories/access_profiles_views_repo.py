from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


class AccessProfilesViewsRepo:
    """
    Legacy read-model repository for Access Profiles (compat only).

    Source:
      - base tables (access_profiles + joins)

    Deprecated:
      - active frontend pages were removed
      - keep only until DAL routers and SQL views are fully retired
    """

    def __init__(self, db: Session):
        self.db = db

    # ============================================================
    # LIST
    # ============================================================

    def list(self) -> list[dict]:
        """List access profiles from SQL read-model tables."""
        return (
            self.db.execute(
                text(
                    """
                    SELECT
                      id,
                      code,
                      name,
                      description,
                      permission,
                      active,
                      used_in_roots_count,
                      created_at,
                      updated_at
                    FROM v_access_profiles_catalog
                    ORDER BY name, id
                    """
                )
            )
            .mappings()
            .all()
        )

    # ============================================================
    # OVERVIEW (DETAIL)
    # ============================================================

    def get_overview(self, profile_id: int) -> dict | None:
        """Full overview of an access profile from SQL read-model tables."""
        profile = (
            self.db.execute(
                text(
                    """
                    SELECT
                      id,
                      code,
                      name,
                      description,
                      permission,
                      active,
                      used_in_roots_count,
                      created_at,
                      updated_at
                    FROM v_access_profiles_catalog
                    WHERE id = :id
                    """
                ),
                {"id": int(profile_id)},
            )
            .mappings()
            .first()
        )

        if not profile:
            return None

        return {
            **dict(profile),
            "subjects": [],
            "users_direct": [],
            "groups_direct": [],
            "users_effective": [],
        }

    def get_console_overview(self, profile_id: int) -> dict | None:
        return (
            self.db.execute(
                text(
                    """
                    SELECT
                      access_profile_id,
                      code,
                      name,
                      description,
                      permission,
                      is_active,
                      created_at,
                      updated_at
                    FROM v_access_profile_console_overview
                    WHERE access_profile_id = :id
                    """
                ),
                {"id": int(profile_id)},
            )
            .mappings()
            .first()
        )

    def list_console_bindings(self, profile_id: int) -> list[dict]:
        return (
            self.db.execute(
                text(
                    """
                    SELECT
                      resource_type,
                      resource_id,
                      resource_name,
                      zone_id,
                      zone_name,
                      created_at
                    FROM v_access_profile_console_bindings
                    WHERE access_profile_id = :id
                    ORDER BY resource_id
                    """
                ),
                {"id": int(profile_id)},
            )
            .mappings()
            .all()
        )

    def list_members(self, profile_id: int) -> list[dict]:
        return (
            self.db.execute(
                text(
                    """
                    SELECT
                      identity_id,
                      identity_kind,
                      display_name,
                      source,
                      added_at
                    FROM v_access_profile_members
                    WHERE access_profile_id = :profile_id
                    ORDER BY display_name ASC
                    """
                ),
                {"profile_id": int(profile_id)},
            )
            .mappings()
            .all()
        )

    # Governed-rule based context lookups are forbidden in V1.
