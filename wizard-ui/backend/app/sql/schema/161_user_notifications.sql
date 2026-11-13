-- Notification centre of the app (the bell): one row per person and per notice, written where the e-mails are
-- decided (new request, decision, end of access, platform breakdown), whether the mail is switched on or not.
-- Idempotent: can be applied again.

CREATE TABLE IF NOT EXISTS user_notifications (
  id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
  identity_id BIGINT NOT NULL,
  notice_key VARCHAR(190) NOT NULL,
  kind VARCHAR(32) NOT NULL,
  severity VARCHAR(16) NOT NULL DEFAULT 'info',
  title VARCHAR(300) NOT NULL,
  body VARCHAR(600) NULL,
  link VARCHAR(300) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  read_at DATETIME NULL,
  UNIQUE KEY uq_user_notifications_notice (identity_id, notice_key),
  KEY ix_user_notifications_unread (identity_id, read_at, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
