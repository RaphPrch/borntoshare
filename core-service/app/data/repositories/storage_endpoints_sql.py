"""SQL of the routes of api/storage_endpoints.py, moved out of them unchanged: each function runs the statement the route
ran and returns the same result (the routes hold no SQL)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session


def same_server_1(db: Session) -> Any:
    """SELECT id, name, host, zone_id FROM storage_endpoints WHERE host IS NOT NULL"""
    return db.execute(
        text("SELECT id, name, host, zone_id FROM storage_endpoints WHERE host IS NOT NULL"),
    )


def assert_zone_of_server_1(db: Session, params: Any) -> Any:
    """SELECT name FROM zones WHERE id = :id"""
    return db.execute(
        text("SELECT name FROM zones WHERE id = :id"),
        params,
    )


def assert_host_free_1(db: Session) -> Any:
    """SELECT id, name, host FROM storage_endpoints WHERE host IS NOT NULL AND LOWER(endpoint_type) <> 'dfs'"""
    return db.execute(
        text("SELECT id, name, host FROM storage_endpoints WHERE host IS NOT NULL AND LOWER(endpoint_type) <> 'dfs'"),
    )


def guard_endpoint_change_1(db: Session, params: Any) -> Any:
    """SELECT id FROM storage_roots WHERE normalized_root_path = :path AND id <> :id LIMIT 1"""
    return db.execute(
        text("SELECT id FROM storage_roots WHERE normalized_root_path = :path AND id <> :id LIMIT 1"),
        params,
    )


def update_endpoint_1(db: Session, params: Any) -> Any:
    """UPDATE storage_endpoints SET zone_id = :zone WHERE id IN :ids"""
    return db.execute(
        text("UPDATE storage_endpoints SET zone_id = :zone WHERE id IN :ids").bindparams(bindparam("ids", expanding=True)),
        params,
    )


def delete_endpoint_share_1(db: Session, params: Any) -> Any:
    """SELECT root_path FROM storage_roots WHERE storage_endpoint_id = :id AND deleted_at IS NULL AND (normalized_roo"""
    return db.execute(
        text("SELECT root_path FROM storage_roots WHERE storage_endpoint_id = :id AND deleted_at IS NULL "
                         "AND (normalized_root_path = :prefix OR normalized_root_path LIKE :below)"),
        params,
    )


def delete_endpoint_1(db: Session, params: Any) -> Any:
    """DELETE FROM infra_component_status WHERE component = :c"""
    return db.execute(
        text("DELETE FROM infra_component_status WHERE component = :c"),
        params,
    )
