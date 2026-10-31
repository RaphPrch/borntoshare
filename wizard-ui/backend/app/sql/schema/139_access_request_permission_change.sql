-- Level of a pending request changed before the decision (read <-> write): what was first asked, by whom it changed and why.
-- Each change is also in the activity log (access_request.permission_changed).
-- Idempotent: can be applied again.

ALTER TABLE access_request_items
  ADD COLUMN IF NOT EXISTS original_permission VARCHAR(32) NULL AFTER permission,
  ADD COLUMN IF NOT EXISTS permission_changed_by BIGINT UNSIGNED NULL AFTER original_permission,
  ADD COLUMN IF NOT EXISTS permission_changed_by_display VARCHAR(255) NULL AFTER permission_changed_by,
  ADD COLUMN IF NOT EXISTS permission_changed_at TIMESTAMP NULL AFTER permission_changed_by_display,
  ADD COLUMN IF NOT EXISTS permission_change_reason VARCHAR(500) NULL AFTER permission_changed_at;
