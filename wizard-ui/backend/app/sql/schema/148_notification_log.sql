-- E-mails sent by BornToShare (Advanced Settings › Notifications): one row per message key, so that a reminder or a
-- notice is never sent twice. Idempotent: can be applied again.

CREATE TABLE IF NOT EXISTS notification_log (
  notice_key VARCHAR(190) NOT NULL PRIMARY KEY,
  recipients VARCHAR(500) NULL,
  status VARCHAR(16) NOT NULL,
  detail VARCHAR(300) NULL,
  sent_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
