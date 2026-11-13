"""SQL of the routes of api/internal_identities.py, moved out of them unchanged: each function runs the statement the route
ran and returns the same result (the routes hold no SQL)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session


def is_entitled_by_group_1(db: Session, params: Any) -> Any:
    """SELECT 1 FROM directory_users du JOIN directory_effective_memberships dem ON dem.directory_user_id = du.id JOI"""
    return db.execute(
        text(
                    """
                    SELECT 1
                    FROM directory_users du
                    JOIN directory_effective_memberships dem ON dem.directory_user_id = du.id
                    JOIN identity_roles ir ON ir.directory_group_id = dem.directory_group_id
                    JOIN identity_sources s ON s.id = du.identity_source_id
                    WHERE du.identity_source_id = :source_id
                      AND s.is_active = 1
                      AND COALESCE(JSON_VALUE(s.capabilities, '$.import_groups'), 'true') NOT IN ('false', '0')
                      AND (
                        LOWER(TRIM(COALESCE(du.external_id, ''))) IN :candidates
                        OR LOWER(TRIM(COALESCE(du.username, ''))) IN :candidates
                        OR LOWER(TRIM(COALESCE(du.upn, ''))) IN :candidates
                        OR LOWER(TRIM(COALESCE(du.email, ''))) IN :candidates
                      )
                    LIMIT 1
                    """
                ).bindparams(bindparam("candidates", expanding=True)),
        params,
    )


def find_existing_identity_1(db: Session, params: Any) -> Any:
    """SELECT i.id, i.username, i.display_name, i.email, i.external_id, i.is_active, COALESCE(i.provisioning_source, """
    return db.execute(
        text(
                        """
                        SELECT
                          i.id,
                          i.username,
                          i.display_name,
                          i.email,
                          i.external_id,
                          i.is_active,
                          COALESCE(i.provisioning_source, 'explicit') AS provisioning_source
                        FROM identities i
                        WHERE i.auth_source = 'ad'
                          AND (:source_id IS NULL OR i.source_id = :source_id)
                          AND (
                            LOWER(TRIM(COALESCE(i.external_id, ''))) = LOWER(:candidate)
                            OR LOWER(TRIM(COALESCE(i.username, ''))) = LOWER(:candidate)
                            OR LOWER(TRIM(COALESCE(i.email, ''))) = LOWER(:candidate)
                          )
                        ORDER BY i.id ASC
                        LIMIT 1
                        """
                    ),
        params,
    )


def resolve_ad_identity_1(db: Session, params: Any) -> Any:
    """SELECT dsu.external_id, dsu.username, dsu.display_name, dsu.email, dsu.is_active FROM directory_snapshot_users"""
    return db.execute(
        text(
                        """
                        SELECT
                          dsu.external_id,
                          dsu.username,
                          dsu.display_name,
                          dsu.email,
                          dsu.is_active
                        FROM directory_snapshot_users dsu
                        JOIN directory_snapshots ds ON ds.id = dsu.snapshot_id
                        WHERE dsu.identity_source_id = :source_id
                          AND (
                            LOWER(TRIM(COALESCE(dsu.external_id, ''))) IN :candidates
                            OR LOWER(TRIM(COALESCE(dsu.dn, ''))) IN :candidates
                            OR LOWER(TRIM(COALESCE(dsu.username, ''))) IN :candidates
                            OR LOWER(TRIM(COALESCE(dsu.upn, ''))) IN :candidates
                            OR LOWER(TRIM(COALESCE(dsu.email, ''))) IN :candidates
                          )
                          AND UPPER(COALESCE(ds.status, '')) IN ('ACTIVE', 'SUCCEEDED')
                        ORDER BY
                          CASE WHEN UPPER(COALESCE(ds.status, '')) = 'ACTIVE' THEN 0 ELSE 1 END,
                          COALESCE(ds.activated_at, ds.completed_at, ds.finished_at, ds.started_at, ds.created_at) DESC,
                          dsu.id DESC
                        LIMIT 1
                        """
                    ),
        params,
    )


def resolve_ad_identity_2(db: Session, params: Any) -> Any:
    """INSERT INTO identities ( source_id, username, type, external_id, display_name, email, auth_source, is_active, """
    return db.execute(
        text(
                                """
                                INSERT INTO identities (
                                  source_id,
                                  username,
                                  type,
                                  external_id,
                                  display_name,
                                  email,
                                  auth_source,
                                  is_active,
                                  snapshot_version,
                                  snapshot_source,
                                  provisioning_source,
                                  status,
                                  created_at,
                                  updated_at
                                ) VALUES (
                                  :source_id,
                                  :username,
                                  'user',
                                  :external_id,
                                  :display_name,
                                  :email,
                                  'ad',
                                  :is_active,
                                  1,
                                  'internal_resolve_ad',
                                  :provisioning_source,
                                  :status,
                                  NOW(),
                                  NOW()
                                )
                                """
                            ),
        params,
    )


def resolve_directory_login_1(db: Session, params: Any) -> Any:
    """SELECT du.identity_source_id FROM directory_users du JOIN identity_sources s ON s.id = du.identity_source_id W"""
    return db.execute(
        text(
                    """
                    SELECT du.identity_source_id
                    FROM directory_users du
                    JOIN identity_sources s ON s.id = du.identity_source_id
                    WHERE s.is_active = 1
                      AND s.auth_enabled = 1
                      AND LOWER(COALESCE(s.type, '')) = 'ad'
                      AND (
                        (:username <> '' AND LOWER(COALESCE(du.username, '')) = :username)
                        OR (:upn_hint <> '' AND (LOWER(COALESCE(du.upn, '')) = :upn_hint OR LOWER(COALESCE(du.email, '')) = :upn_hint))
                      )
                    ORDER BY
                      CASE
                        WHEN :domain_hint <> '' AND (
                          LOWER(COALESCE(s.domain_name, '')) = :domain_hint
                          OR SUBSTRING_INDEX(LOWER(COALESCE(s.domain_name, '')), '.', 1) = SUBSTRING_INDEX(:domain_hint, '.', 1)
                        ) THEN 0
                        ELSE 1
                      END,
                      s.auth_priority ASC,
                      s.id ASC
                    LIMIT 1
                    """
                ),
        params,
    )


def resolve_login_identity_1(db: Session, params: Any) -> Any:
    """SELECT i.id, i.username, i.display_name, i.email, i.auth_source, i.source_id, i.external_id, i.is_active, i.st"""
    return db.execute(
        text(
                    """
                    SELECT
                      i.id,
                      i.username,
                      i.display_name,
                      i.email,
                      i.auth_source,
                      i.source_id,
                      i.external_id,
                      i.is_active,
                      i.status,
                      i.type,
                      COALESCE(i.provisioning_source, 'explicit') AS provisioning_source
                    FROM identities i
                    LEFT JOIN identity_sources s ON s.id = i.source_id
                    WHERE LOWER(COALESCE(i.type, 'user')) = 'user'
                      AND COALESCE(i.provisioning_source, 'explicit') <> 'legacy_auto_snapshot'
                      -- Identities created by an SSO provider sign in through it only, never with a password
                      AND LOWER(COALESCE(i.auth_source, '')) <> 'oidc'
                      AND (
                        (:username <> '' AND LOWER(TRIM(COALESCE(i.username, ''))) = LOWER(:username))
                        OR
                        (:upn_hint <> '' AND LOWER(TRIM(COALESCE(i.email, ''))) = LOWER(:upn_hint))
                      )
                      -- AD identities only through a source that is active and allows authentication
                      AND (
                        LOWER(COALESCE(i.auth_source, '')) <> 'ad'
                        OR (s.id IS NOT NULL AND s.is_active = 1 AND s.auth_enabled = 1)
                      )
                    ORDER BY
                      -- The source of the domain typed by the user (DOMAIN backslash user, or user@domain) first
                      CASE
                        WHEN :domain_hint <> '' AND (
                          LOWER(COALESCE(s.domain_name, '')) = :domain_hint
                          OR SUBSTRING_INDEX(LOWER(COALESCE(s.domain_name, '')), '.', 1) = SUBSTRING_INDEX(:domain_hint, '.', 1)
                        ) THEN 0
                        ELSE 1
                      END,
                      CASE
                        WHEN :upn_hint <> '' AND LOWER(TRIM(COALESCE(i.email, ''))) = LOWER(:upn_hint) THEN 0
                        WHEN :domain_hint <> '' AND LOWER(COALESCE(i.auth_source, '')) = 'ad' THEN 1
                        WHEN :domain_hint = '' AND :upn_hint = '' AND LOWER(COALESCE(i.auth_source, '')) = 'local' THEN 2
                        WHEN LOWER(COALESCE(i.auth_source, '')) = 'ad' THEN 3
                        ELSE 4
                      END,
                      i.is_active DESC,
                      i.id ASC
                    LIMIT 1
                    """
                ),
        params,
    )
