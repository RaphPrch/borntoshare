"""Encrypted secrets in the database (secret_items). Only this service holds the key."""
from __future__ import annotations

import os
from typing import Any, Optional

import pymysql
from pymysql.cursors import DictCursor

from core.errors import SecretPersistenceFailureError


def _connect():
    return pymysql.connect(
        host=os.getenv("DB_HOST", ""),
        port=int(os.getenv("DB_PORT") or 3306),
        user=os.getenv("DB_USER", ""),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", ""),
        connect_timeout=5,
        read_timeout=10,
        write_timeout=10,
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=True,
    )


def _run(sql: str, params: tuple, *, ref: str) -> Any:
    try:
        connection = _connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                return cursor.fetchone() if sql.lstrip().upper().startswith("SELECT") else None
        finally:
            connection.close()
    except pymysql.MySQLError as exc:
        raise SecretPersistenceFailureError(
            message="The secret store (database) is not available", ref=ref, provider="database"
        ) from exc


def get(ref: str) -> Optional[dict[str, Any]]:
    return _run("SELECT iv, ciphertext, key_id FROM secret_items WHERE ref = %s", (ref,), ref=ref)


def put(ref: str, name: str, iv: str, ciphertext: str, key_id: str) -> None:
    _run(
        """
        INSERT INTO secret_items (ref, name, iv, ciphertext, key_id) VALUES (%s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE iv = VALUES(iv), ciphertext = VALUES(ciphertext), key_id = VALUES(key_id)
        """,
        (ref, name, iv, ciphertext, key_id),
        ref=ref,
    )


def delete(ref: str) -> None:
    _run("DELETE FROM secret_items WHERE ref = %s", (ref,), ref=ref)
