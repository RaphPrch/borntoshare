"""SQL of the routes of api/zones.py, moved out of them unchanged: each function runs the statement the route
ran and returns the same result (the routes hold no SQL)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def get_zone_write_row_1(db: Session, params: Any) -> Any:
    """SELECT id, name, code, description FROM zones WHERE id = :id LIMIT 1"""
    return db.execute(
        text(
                    """
                    SELECT
                      id,
                      name,
                      code,
                      description
                    FROM zones
                    WHERE id = :id
                    LIMIT 1
                    """
                ),
        params,
    )


def put_zone_provisioning_policy_1(db: Session, params: Any) -> Any:
    """INSERT INTO zone_provisioning_policy (zone_id, enabled, policy_mode, ou_strategy, base_ou_dn, static_ou_dn) VA"""
    return db.execute(
        text(
                    """
                    INSERT INTO zone_provisioning_policy
                      (zone_id, enabled, policy_mode, ou_strategy, base_ou_dn, static_ou_dn)
                    VALUES
                      (:zone_id, :enabled, :policy_mode, :ou_strategy, :base_ou_dn, :static_ou_dn)
                    ON DUPLICATE KEY UPDATE
                      enabled = VALUES(enabled),
                      policy_mode = VALUES(policy_mode),
                      ou_strategy = VALUES(ou_strategy),
                      base_ou_dn = VALUES(base_ou_dn),
                      static_ou_dn = VALUES(static_ou_dn)
                    """
                ),
        params,
    )


def refuse_duplicate_zone_1(db: Session, params: Any) -> Any:
    """SELECT 1 FROM zones WHERE id <> :excluding AND (LOWER(name) = LOWER(:name) OR (:code <> '' AND LOWER(code) = L"""
    return db.execute(
        text(
                    """
                    SELECT 1 FROM zones
                    WHERE id <> :excluding AND (LOWER(name) = LOWER(:name) OR (:code <> '' AND LOWER(code) = LOWER(:code)))
                    LIMIT 1
                    """
                ),
        params,
    )


def create_zone_1(db: Session, params: Any) -> Any:
    """INSERT INTO zones (name, code, description) VALUES (:name, :code, :description)"""
    return db.execute(
        text(
                    """
                    INSERT INTO zones (name, code, description)
                    VALUES (:name, :code, :description)
                    """
                ),
        params,
    )


def create_zone_2(db: Session) -> Any:
    """SELECT LAST_INSERT_ID()"""
    return db.execute(
        text("SELECT LAST_INSERT_ID()"),
    )


def delete_zone_1(db: Session, params: Any) -> Any:
    """SELECT COUNT(1) FROM storage_endpoints WHERE zone_id = :zone_id"""
    return db.execute(
        text(
                        """
                        SELECT COUNT(1)
                        FROM storage_endpoints
                        WHERE zone_id = :zone_id
                        """
                    ),
        params,
    )


def delete_zone_2(db: Session, params: Any) -> Any:
    """DELETE FROM zones WHERE id = :zone_id"""
    return db.execute(
        text(
                    """
                    DELETE FROM zones
                    WHERE id = :zone_id
                    """
                ),
        params,
    )
