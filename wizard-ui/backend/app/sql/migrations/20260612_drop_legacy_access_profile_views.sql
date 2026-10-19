-- BornToShare
-- Live DB cleanup: drop deprecated access_profiles legacy views.
--
-- Scope:
-- - drops legacy residual views only, including dependent child views
-- - no table changes
-- - no data deletion
-- - no seed changes
--
-- Preconditions:
-- - active frontend pages for access_profiles were removed
-- - /access-profiles DAL routes are deprecated or return 410 Gone
-- - SQL source view files no longer recreate these views
--
-- Rollback:
-- - no automatic rollback is provided here
-- - if needed, recreate views from the historical SQL definitions
--   kept in version control, knowing they are deprecated

-- Child views depending on legacy members / catalog views
DROP VIEW IF EXISTS v_access_profile_users_effective_snapshot;
DROP VIEW IF EXISTS v_access_profile_groups_direct;
DROP VIEW IF EXISTS v_access_profile_users_direct;

-- Console / dashboard / zone views next
DROP VIEW IF EXISTS v_dashboard_access_requests_by_profile;
DROP VIEW IF EXISTS v_zone_console_access_profiles;
DROP VIEW IF EXISTS v_access_profile_console_bindings;
DROP VIEW IF EXISTS v_access_profile_console_overview;

-- Detail / binding helper views next
DROP VIEW IF EXISTS v_access_profile_group_mappings;
DROP VIEW IF EXISTS v_access_profile_members;
DROP VIEW IF EXISTS v_access_profiles_overview;

-- Main catalog / list views last
DROP VIEW IF EXISTS v_access_profiles_catalog;
DROP VIEW IF EXISTS v_access_profiles;
