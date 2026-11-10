-- Each measure of a governed folder (size, files, sub-folders, cold data, clutter): the growth curve and the date
-- the quota will be full. And the corrections asked to guardians for the passwords found in their folders: due date,
-- scan again at the due date, closed by itself when the files are gone. Idempotent: can be applied again.

-- (The history of the measures moved to the 5S module: b2s_fives.content_history, created by the wizard)

CREATE TABLE IF NOT EXISTS sensitivity_remediations (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  storage_root_id BIGINT NOT NULL,
  -- open: the guardians have until due_at · overdue: still there at the due date · done: gone · cancelled
  status VARCHAR(16) NOT NULL DEFAULT 'open',
  files_at_request INT UNSIGNED NOT NULL DEFAULT 0,
  paths_json LONGTEXT NULL,
  note VARCHAR(500) NULL,
  requested_by VARCHAR(190) NULL,
  requested_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  due_at DATETIME NOT NULL,
  rescan_requested_at DATETIME NULL,
  closed_at DATETIME NULL,
  closed_by VARCHAR(190) NULL,
  KEY ix_remediations_root (storage_root_id, status),
  KEY ix_remediations_due (status, due_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
