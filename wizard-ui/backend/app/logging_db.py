from __future__ import annotations

import json
import hashlib
import logging
import os
import threading
import traceback
import uuid
from typing import Any, Optional

from .db import get_connection

DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_RETENTION_ENABLED = True
DEFAULT_RETENTION_DAYS = 180
ALLOWED_LEVELS = {"DEBUG", "INFO", "WARN", "ERROR"}

ALLOWED_AUDIT_ACTOR_TYPES = {"user", "service", "system"}
ALLOWED_AUDIT_RESULTS = {"success", "failure", "denied", "in_progress"}
ALLOWED_AUDIT_SEVERITIES = {"info", "warning", "error", "critical"}
ALLOWED_AUDIT_SCOPES = {"business", "technical"}


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


def _normalize_actor_type(actor_type: str | None) -> str:
    value = str(actor_type or "system").strip().lower()
    return value if value in ALLOWED_AUDIT_ACTOR_TYPES else "system"


def _normalize_result(outcome: str | None) -> str:
    value = str(outcome or "success").strip().lower()
    return value if value in ALLOWED_AUDIT_RESULTS else "success"


def _normalize_scope(scope: str | None) -> str:
    value = str(scope or "business").strip().lower()
    return value if value in ALLOWED_AUDIT_SCOPES else "business"


def _result_to_severity(result: str) -> str:
    mapping = {
        "success": "info",
        "failure": "error",
        "denied": "warning",
        "in_progress": "info",
    }
    severity = mapping.get(result, "info")
    return severity if severity in ALLOWED_AUDIT_SEVERITIES else "info"


def _json_to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, (bytes, bytearray)):
        try:
            value = value.decode("utf-8", errors="ignore")
        except Exception:
            return {}
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


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

    def _next_event_hash(self, cur, payload: dict[str, Any]) -> tuple[str, str | None]:
        cur.execute("SELECT hash_current FROM audit_event ORDER BY event_time DESC, id DESC LIMIT 1")
        row = cur.fetchone()
        prev_hash = str(row[0]) if row and row[0] else None
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        seed = f"{prev_hash or ''}|{canonical}".encode("utf-8", errors="ignore")
        event_hash = hashlib.sha256(seed).hexdigest()
        return (event_hash, prev_hash)

    def save_config(
        self,
        *,
        level: str,
        retention_enabled: bool,
        retention_days: int,
    ) -> dict[str, Any]:
        self.ensure_schema()

        normalized_level = normalize_level(level)
        normalized_days = max(1, int(retention_days))

        conn = self._connect()
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO wizard_logging_settings(id, level, retention_enabled, retention_days)
                VALUES(1, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                  level = VALUES(level),
                  retention_enabled = VALUES(retention_enabled),
                  retention_days = VALUES(retention_days)
                """,
                (normalized_level, 1 if retention_enabled else 0, normalized_days),
            )
            conn.commit()
        finally:
            cur.close()
            conn.close()

        return {
            "level": normalized_level,
            "retentionEnabled": retention_enabled,
            "retentionDays": normalized_days,
        }

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

    def list_logs(self, *, limit: int = 100, level: Optional[str] = None) -> list[dict[str, Any]]:
        self.ensure_schema()

        safe_limit = max(1, min(int(limit or 100), 500))
        params: list[Any] = []
        where = ""

        if level:
            where = "WHERE level = %s"
            params.append(normalize_level(level))

        conn = self._connect()
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute(
                f"""
                SELECT id, created_at, level, logger_name, module_name, message, request_id
                FROM wizard_logs
                {where}
                ORDER BY id DESC
                LIMIT %s
                """,
                tuple(params + [safe_limit]),
            )
            rows = cur.fetchall() or []
            out = []
            for r in rows:
                out.append(
                    {
                        "id": r.get("id"),
                        "created_at": r.get("created_at").isoformat() if r.get("created_at") else None,
                        "level": r.get("level"),
                        "logger_name": r.get("logger_name"),
                        "module_name": r.get("module_name"),
                        "message": r.get("message"),
                        "request_id": r.get("request_id"),
                    }
                )
            return out
        finally:
            cur.close()
            conn.close()

    def purge_logs(
        self,
        *,
        older_than_days: Optional[int] = None,
        all_logs: bool = False,
    ) -> int:
        self.ensure_schema()

        if all_logs:
            sql = "DELETE FROM wizard_logs"
            params: tuple[Any, ...] = tuple()
        else:
            if older_than_days is None:
                cfg = self.get_config()
                if not cfg.get("retentionEnabled", True):
                    return 0
                older_than_days = int(cfg.get("retentionDays", DEFAULT_RETENTION_DAYS))

            older_than_days = max(1, int(older_than_days))
            sql = "DELETE FROM wizard_logs WHERE created_at < (NOW() - INTERVAL %s DAY)"
            params = (older_than_days,)

        conn = self._connect()
        cur = conn.cursor()
        try:
            cur.execute(sql, params)
            deleted = int(cur.rowcount or 0)
            conn.commit()
            return deleted
        finally:
            cur.close()
            conn.close()

    def write_activity_event(
        self,
        *,
        actor_type: str,
        actor_id: int | str | None,
        actor_display: str | None,
        action: str,
        outcome: str,
        event_category: str | None = None,
        event_scope: str | None = None,
        target_type: str | None,
        target_id: int | None,
        target_display: str | None,
        metadata_json: dict[str, Any] | None,
        request_id: str | None,
        correlation_id: str | None,
        zone_id: int | None = None,
        root_id: int | None = None,
        endpoint_id: int | None = None,
        severity: str | None = None,
    ) -> str | None:
        if not self.is_enabled():
            return None

        self.ensure_schema()

        conn = self._connect()
        cur = conn.cursor()
        try:
            event_uuid = uuid.uuid4()
            normalized_actor_type = _normalize_actor_type(actor_type)
            normalized_result = _normalize_result(outcome)
            normalized_scope = _normalize_scope(event_scope)
            normalized_severity = str(severity or _result_to_severity(normalized_result)).strip().lower()
            if normalized_severity not in ALLOWED_AUDIT_SEVERITIES:
                normalized_severity = _result_to_severity(normalized_result)
            resolved_correlation_id = str(correlation_id or request_id or event_uuid)
            source_service = str(os.getenv("SERVICE_NAME", "wizard-ui"))
            metadata: dict[str, Any] = {
                **(metadata_json or {}),
                "actor_display": actor_display,
                "target_display": target_display,
                "request_id": request_id,
            }

            payload = {
                "id": str(event_uuid),
                "actor_type": normalized_actor_type,
                "actor_id": str(actor_id if actor_id is not None else "system"),
                "action": action,
                "entity_type": target_type,
                "entity_id": None if target_id is None else str(target_id),
                "zone_id": zone_id,
                "root_id": root_id,
                "endpoint_id": endpoint_id,
                "result": normalized_result,
                "severity": normalized_severity,
                "correlation_id": resolved_correlation_id,
                "source_service": source_service,
                "metadata_json": {
                    **metadata,
                    "event_category": event_category,
                    "event_scope": normalized_scope,
                },
            }
            event_hash, prev_hash = self._next_event_hash(cur, payload)

            cur.execute(
                """
                INSERT INTO audit_event(
                  id, event_time,
                  actor_type, actor_id,
                  action, entity_type, entity_id, zone_id, root_id, endpoint_id,
                  result, severity,
                  correlation_id,
                  source_service,
                  metadata_json,
                  hash_prev, hash_current
                )
                VALUES(%s, NOW(6), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    event_uuid.bytes,
                    normalized_actor_type,
                    str(actor_id if actor_id is not None else "system"),
                    action,
                    target_type,
                    None if target_id is None else str(target_id),
                    zone_id,
                    root_id,
                    endpoint_id,
                    normalized_result,
                    normalized_severity,
                    resolved_correlation_id,
                    source_service,
                    json.dumps(payload.get("metadata_json") or {}, ensure_ascii=False),
                    prev_hash,
                    event_hash,
                ),
            )
            conn.commit()
            return str(event_uuid)
        finally:
            cur.close()
            conn.close()

    def list_activity_events(
        self,
        *,
        limit: int = 100,
        actor_id: int | None = None,
        target_type: str | None = None,
        target_id: int | None = None,
        zone_id: int | None = None,
        root_id: int | None = None,
        endpoint_id: int | None = None,
        event_category: str | None = None,
        event_scope: str | None = None,
        start_at: str | None = None,
        end_at: str | None = None,
    ) -> list[dict[str, Any]]:
        self.ensure_schema()
        safe_limit = max(1, min(int(limit or 100), 500))

        filters: list[str] = []
        params: list[Any] = []
        if actor_id is not None:
            filters.append("actor_id = %s")
            params.append(str(actor_id))
        if target_type:
            filters.append("entity_type = %s")
            params.append(str(target_type))
        if target_id is not None:
            filters.append("entity_id = %s")
            params.append(str(target_id))
        if zone_id is not None:
            filters.append("zone_id = %s")
            params.append(int(zone_id))
        if root_id is not None:
            filters.append("root_id = %s")
            params.append(int(root_id))
        if endpoint_id is not None:
            filters.append("endpoint_id = %s")
            params.append(int(endpoint_id))
        if start_at:
            filters.append("event_time >= %s")
            params.append(str(start_at))
        if end_at:
            filters.append("event_time <= %s")
            params.append(str(end_at))

        where = f"WHERE {' AND '.join(filters)}" if filters else ""

        conn = self._connect()
        cur = conn.cursor(dictionary=True)
        try:
            cur.execute(
                f"""
                SELECT
                  id, event_time,
                  actor_type, actor_id,
                  action, result,
                  entity_type, entity_id, zone_id, root_id, endpoint_id, severity,
                  correlation_id,
                  metadata_json, hash_current, hash_prev
                FROM audit_event
                {where}
                ORDER BY event_time DESC, id DESC
                LIMIT %s
                """,
                tuple(params + [safe_limit]),
            )
            rows = cur.fetchall() or []
            out: list[dict[str, Any]] = []
            for r in rows:
                event_id = r.get("id")
                if isinstance(event_id, (bytes, bytearray)) and len(event_id) == 16:
                    event_id = str(uuid.UUID(bytes=bytes(event_id)))

                metadata = _json_to_dict(r.get("metadata_json"))
                out.append(
                    {
                        "id": event_id,
                        "occurred_at": r.get("event_time").isoformat() if r.get("event_time") else None,
                        "actor_type": r.get("actor_type"),
                        "actor_id": r.get("actor_id"),
                        "actor_display": metadata.get("actor_display"),
                        "action": r.get("action"),
                        "event_category": metadata.get("event_category"),
                        "event_scope": metadata.get("event_scope"),
                        "outcome": r.get("result"),
                        "result": r.get("result"),
                        "severity": r.get("severity"),
                        "target_type": r.get("entity_type"),
                        "target_id": r.get("entity_id"),
                        "entity_type": r.get("entity_type"),
                        "entity_id": r.get("entity_id"),
                        "zone_id": r.get("zone_id"),
                        "root_id": r.get("root_id"),
                        "storage_root_id": r.get("root_id"),
                        "endpoint_id": r.get("endpoint_id"),
                        "target_display": metadata.get("target_display"),
                        "request_id": metadata.get("request_id"),
                        "correlation_id": r.get("correlation_id"),
                        "metadata_json": metadata,
                        "event_hash": r.get("hash_current"),
                        "prev_hash": r.get("hash_prev"),
                    }
                )
            return out
        finally:
            cur.close()
            conn.close()


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
