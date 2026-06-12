# SQL Migrations

`20260612_drop_legacy_access_profile_views.sql` removes only live residual legacy views related to `access_profiles`.

These views are deprecated:
- active UI pages were removed
- DAL compatibility routes were retired or downgraded
- SQL source view files no longer recreate them

The script:
- drops views only
- does not drop tables
- does not delete data
- also drops dependent child views that still reference deprecated access-profile views in live DB

Rollback is manual only by restoring the previous view definitions from version control if strictly needed.
