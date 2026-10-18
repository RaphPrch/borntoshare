from __future__ import annotations

import json
import logging
import os
import threading
import traceback
from typing import Any, Optional

from .db import get_connection

DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_RETENTION_ENABLED = True
DEFAULT_RETENTION_DAYS = 180
ALLOWED_LEVELS = {"DEBUG", "INFO", "WARN", "ERROR"}


def _as_bool(value: str | None, default: bool = True) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def normalize_level(level: str | None) -> str:
    raw = str(level or DEFAULT_LOG_LEVEL).upper()
    if raw == "WARNING":
        return "WARN"
    if raw not in ALLOWED_LEVELS:
        return DEFAULT_LOG_LEVEL
    return raw


class WizardLoggingStore:
    def __init__(self) -> None:
        self._schema_ready = False
        self._schema_lock = threading.Lock()
        self._logger = logging.getLogger("wizard.logging.db")

    def is_enabled(self) -> bool:
        return _as_bool(os.getenv("WIZARD_LOG_DB_ENABLED", "true"), default=True)

    def db_name(self) -> str:
        return (
            os.getenv("WIZARD_LOG_DB_NAME")
            or os.getenv("DB_NAME")
            or "borntoshare"
        )

    def _root_cfg(self) -> dict | None:
        host = os.getenv("WIZARD_LOG_DB_HOST", "").strip()
        user = os.getenv("WIZARD_LOG_DB_USER", "").strip()
        if not host or not user:
            return None

        return {
            "host": host,
            "port": int(os.getenv("WIZARD_LOG_DB_PORT", "3306")),
            "user": user,
            "password": os.getenv("WIZARD_LOG_DB_PASSWORD", ""),
            "database": self.db_name(),
        }

    def _connect(self):
        return get_connection(
            database=True,
            db_name=self.db_name(),
            root_cfg=self._root_cfg(),
            log_connection=False,
        )

    def _ensure_index(self, cursor, table: str, index_name: str, ddl: str) -> None:
        cursor.execute(f"SHOW INDEX FROM `{table}` WHERE Key_name = %s", (index_name,))
        exists = cursor.fetchone() is not None
        # mysql-connector may raise "Unread result found" on subsequent execute/close
        # when the result set from SHOW INDEX is not fully consumed.
        cursor.fetchall()
        if not exists:
            cursor.execute(ddl)

    def ensure_schema(self) -> None:
        if not self.is_enabled():
            return

        if self._schema_ready:
            return

        with self._schema_lock:
            if self._schema_ready:
                return

            conn = self._connect()
            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS wizard_logging_settings (
                      id TINYINT UNSIGNED NOT NULL PRIMARY KEY,
                      level VARCHAR(10) NOT NULL DEFAULT 'INFO',
                      retention_enabled TINYINT(1) NOT NULL DEFAULT 1,
                      retention_days INT UNSIGNED NOT NULL DEFAULT 180,
                      updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """
                )

                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS wizard_logs (
                      id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                      created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                      level VARCHAR(10) NOT NULL,
                      logger_name VARCHAR(191) NOT NULL,
                      module_name VARCHAR(191) NULL,
                      message TEXT NOT NULL,
                      request_id VARCHAR(64) NULL,
                      context_json JSON NULL,
                      exception_text TEXT NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """
                )

                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS audit_event (
                      id BINARY(16) NOT NULL PRIMARY KEY,
                      event_time DATETIME(6) NOT NULL,
                      actor_type VARCHAR(20) NOT NULL,
                      actor_id VARCHAR(255) NULL,
                      action VARCHAR(120) NOT NULL,
                      entity_type VARCHAR(80) NULL,
                      entity_id VARCHAR(255) NULL,
                      zone_id BIGINT NULL,
                      root_id BIGINT NULL,
                      endpoint_id BIGINT NULL,
                      result VARCHAR(20) NOT NULL,
                      severity VARCHAR(20) NOT NULL,
                      correlation_id VARCHAR(64) NOT NULL,
                      source_service VARCHAR(100) NOT NULL,
                      metadata_json JSON NULL,
                      hash_prev CHAR(64) NULL,
                      hash_current CHAR(64) NOT NULL
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """
                )

                # Forward-compatible migrations for existing schemas (best effort).
                for ddl in (
                    "ALTER TABLE audit_event ADD COLUMN IF NOT EXISTS zone_id BIGINT NULL AFTER entity_id",
                    "ALTER TABLE audit_event ADD COLUMN IF NOT EXISTS root_id BIGINT NULL AFTER zone_id",
                    "ALTER TABLE audit_event ADD COLUMN IF NOT EXISTS endpoint_id BIGINT NULL AFTER root_id",
                ):
                    try:
                        cur.execute(ddl)
                    except Exception:
                        pass

                self._ensure_index(
                    cur,
                    "wizard_logs",
                    "idx_wizard_logs_created_at",
                    "CREATE INDEX idx_wizard_logs_created_at ON wizard_logs(created_at)",
                )
                self._ensure_index(
                    cur,
                    "wizard_logs",
                    "idx_wizard_logs_level_created_at",
                    "CREATE INDEX idx_wizard_logs_level_created_at ON wizard_logs(level, created_at)",
                )
                self._ensure_index(
                    cur,
                    "audit_event",
                    "idx_audit_time",
                    "CREATE INDEX idx_audit_time ON audit_event(event_time)",
                )
                self._ensure_index(
                    cur,
                    "audit_event",
                    "idx_audit_actor",
                    "CREATE INDEX idx_audit_actor ON audit_event(actor_type, actor_id, event_time)",
                )
                self._ensure_index(
                    cur,
                    "audit_event",
                    "idx_audit_entity",
                    "CREATE INDEX idx_audit_entity ON audit_event(entity_type, entity_id, event_time)",
                )
                self._ensure_index(
                    cur,
                    "audit_event",
                    "idx_audit_entity_created",
                    "CREATE INDEX idx_audit_entity_created ON audit_event(entity_type, entity_id, event_time)",
                )
                self._ensure_index(
                    cur,
                    "audit_event",
                    "idx_audit_corr_id",
                    "CREATE INDEX idx_audit_corr_id ON audit_event(correlation_id)",
                )
                self._ensure_index(
                    cur,
                    "audit_event",
                    "idx_audit_action",
                    "CREATE INDEX idx_audit_action ON audit_event(action, event_time)",
                )
                self._ensure_index(
                    cur,
                    "audit_event",
                    "idx_audit_zone",
                    "CREATE INDEX idx_audit_zone ON audit_event(zone_id, event_time)",
                )
                self._ensure_index(
                    cur,
                    "audit_event",
                    "idx_audit_root",
                    "CREATE INDEX idx_audit_root ON audit_event(root_id, event_time)",
                )
                self._ensure_index(
                    cur,
                    "audit_event",
                    "idx_audit_endpoint",
                    "CREATE INDEX idx_audit_endpoint ON audit_event(endpoint_id, event_time)",
                )
                self._ensure_index(
                    cur,
                    "audit_event",
                    "idx_audit_created_at",
                    "CREATE INDEX idx_audit_created_at ON audit_event(event_time)",
                )

                cur.execute(
                    """
                    INSERT INTO wizard_logging_settings(id, level, retention_enabled, retention_days)
                    VALUES(1, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE id = id
                    """,
                    (DEFAULT_LOG_LEVEL, 1 if DEFAULT_RETENTION_ENABLED else 0, DEFAULT_RETENTION_DAYS),
                )

                conn.commit()
                self._schema_ready = True
            finally:
                cur.close()
                conn.close()

    def get_config(self) -> dict[str, Any]:
        self.ensure_schema()

        conn = self._connect()
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute(
                "SELECT level, retention_enabled, retention_days FROM wizard_logging_settings WHERE id = 1"
            )
            row = cur.fetchone() or {}
            level = normalize_level(row.get("level"))
            retention_enabled = bool(int(row.get("retention_enabled", 1) or 1))
            retention_days = int(row.get("retention_days", DEFAULT_RETENTION_DAYS) or DEFAULT_RETENTION_DAYS)

            return {
                "level": level,
                "retentionEnabled": retention_enabled,
                "retentionDays": max(1, retention_days),
            }
        finally:
            cur.close()
            conn.close()

    def write_log(
        self,
        *,
        level: str,
        logger_name: str,
        module_name: Optional[str],
        message: str,
        request_id: Optional[str] = None,
        context: Optional[dict[str, Any]] = None,
        exception_text: Optional[str] = None,
    ) -> None:
        if not self.is_enabled():
            return

        self.ensure_schema()

        conn = self._connect()
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO wizard_logs(level, logger_name, module_name, message, request_id, context_json, exception_text)
                VALUES(%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    normalize_level(level),
                    str(logger_name or "wizard"),
                    module_name,
                    message,
                    request_id,
                    json.dumps(context or {}, ensure_ascii=False),
                    exception_text,
                ),
            )
            conn.commit()
        except Exception:
            # Never break app flow because of logging persistence failures.
            pass
        finally:
            try:
                cur.close()
                conn.close()
            except Exception:
                pass

class DBLogHandler(logging.Handler):
    def __init__(self, store: WizardLoggingStore):
        super().__init__()
        self._store = store

    def emit(self, record: logging.LogRecord) -> None:
        try:
            exc_text = None
            if record.exc_info:
                exc_text = "".join(traceback.format_exception(*record.exc_info))

            context = {}
            for key in ("path", "method", "status_code"):
                value = getattr(record, key, None)
                if value is not None:
                    context[key] = value

            self._store.write_log(
                level=record.levelname,
                logger_name=record.name,
                module_name=getattr(record, "module", None),
                message=record.getMessage(),
                request_id=getattr(record, "request_id", None),
                context=context,
                exception_text=exc_text,
            )
        except Exception:
            # Never propagate logging handler errors.
            return


logging_store = WizardLoggingStore()
