"""SQL of the routes of api/identity_list.py, moved out of them unchanged: each function runs the statement the route
ran and returns the same result (the routes hold no SQL)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session


def pick_identity_source_1(db: Session) -> Any:
    """SELECT id FROM identity_sources WHERE type = 'ad' AND is_active = 1 ORDER BY id ASC LIMIT 1"""
    return db.execute(
        text(
                    """
                    SELECT id
                    FROM identity_sources
                    WHERE type = 'ad' AND is_active = 1
                    ORDER BY id ASC
                    LIMIT 1
                    """
                ),
    )


def pick_local_identity_source_id_1(db: Session, params: Any) -> Any:
    """SELECT id FROM identity_sources WHERE id = :id AND LOWER(COALESCE(type, '')) IN ('local', 'internal') AND is_a"""
    return db.execute(
        text(
                        """
                        SELECT id
                        FROM identity_sources
                        WHERE id = :id
                          AND LOWER(COALESCE(type, '')) IN ('local', 'internal')
                          AND is_active = 1
                        LIMIT 1
                        """
                    ),
        params,
    )


def pick_local_identity_source_id_2(db: Session) -> Any:
    """SELECT id FROM identity_sources WHERE LOWER(COALESCE(type, '')) IN ('local', 'internal') AND is_active = 1 ORD"""
    return db.execute(
        text(
                    """
                    SELECT id
                    FROM identity_sources
                    WHERE LOWER(COALESCE(type, '')) IN ('local', 'internal')
                      AND is_active = 1
                    ORDER BY id ASC
                    LIMIT 1
                    """
                ),
    )


def pick_local_identity_source_id_3(db: Session) -> Any:
    """SELECT source_id AS id FROM identities WHERE LOWER(COALESCE(auth_source, '')) IN ('local', 'internal') AND sou"""
    return db.execute(
        text(
                    """
                    SELECT source_id AS id
                    FROM identities
                    WHERE LOWER(COALESCE(auth_source, '')) IN ('local', 'internal')
                      AND source_id IS NOT NULL
                    ORDER BY id ASC
                    LIMIT 1
                    """
                ),
    )


def ensure_role_id_1(db: Session, params: Any) -> Any:
    """SELECT id FROM roles WHERE code = :code LIMIT 1"""
    return db.execute(
        text(
                    """
                    SELECT id
                    FROM roles
                    WHERE code = :code
                    LIMIT 1
                    """
                ),
        params,
    )


def ensure_role_id_2(db: Session, params: Any) -> Any:
    """INSERT INTO roles (code, label, description, created_at, updated_at) VALUES (:code, :label, :description, NOW("""
    return db.execute(
        text(
                    """
                    INSERT INTO roles (code, label, description, created_at, updated_at)
                    VALUES (:code, :label, :description, NOW(), NOW())
                    """
                ),
        params,
    )


def ensure_role_id_3(db: Session, params: Any) -> Any:
    """SELECT id FROM roles WHERE code = :code LIMIT 1"""
    return db.execute(
        text(
                    """
                    SELECT id
                    FROM roles
                    WHERE code = :code
                    LIMIT 1
                    """
                ),
        params,
    )


def other_admin_exists_1(db: Session, params: Any) -> Any:
    """SELECT 1 FROM identity_roles ir JOIN roles r ON r.id = ir.role_id AND r.code = 'platform_admin' LEFT JOIN iden"""
    return db.execute(
        text(
                    """
                    SELECT 1
                    FROM identity_roles ir
                    JOIN roles r ON r.id = ir.role_id AND r.code = 'platform_admin'
                    LEFT JOIN identities i ON i.id = ir.identity_id
                    WHERE (ir.identity_id IS NOT NULL AND i.is_active = 1 AND ir.identity_id <> COALESCE(:identity, 0))
                       OR (ir.directory_group_id IS NOT NULL AND ir.directory_group_id <> COALESCE(:grp, 0))
                    LIMIT 1
                    """
                ),
        params,
    )


def subject_is_admin_1(db: Session, params: Any) -> Any:
    """SELECT 1 FROM identity_roles ir JOIN roles r ON r.id = ir.role_id AND r.code = 'platform_admin' WHERE (:identi"""
    return db.execute(
        text(
                    """
                    SELECT 1 FROM identity_roles ir JOIN roles r ON r.id = ir.role_id AND r.code = 'platform_admin'
                    WHERE (:identity IS NOT NULL AND ir.identity_id = :identity) OR (:grp IS NOT NULL AND ir.directory_group_id = :grp)
                    LIMIT 1
                    """
                ),
        params,
    )


def is_last_local_admin_1(db: Session) -> Any:
    """SELECT i.id FROM identity_roles ir JOIN roles r ON r.id = ir.role_id AND r.code = 'platform_admin' JOIN identi"""
    return db.execute(
        text(
                    """
                    SELECT i.id FROM identity_roles ir JOIN roles r ON r.id = ir.role_id AND r.code = 'platform_admin'
                    JOIN identities i ON i.id = ir.identity_id
                    WHERE LOWER(i.auth_source) = 'local' AND i.is_active = 1
                    """
                ),
    )


def orphaned_folders_1(db: Session, params: Any) -> Any:
    """SELECT sr.id, sr.name, sr.root_path FROM storage_root_roles r JOIN storage_roots sr ON sr.id = r.root_id WHERE"""
    return db.execute(
        text(
                    """
                    SELECT sr.id, sr.name, sr.root_path
                    FROM storage_root_roles r JOIN storage_roots sr ON sr.id = r.root_id
                    WHERE r.identity_id = :id AND LOWER(r.role) = 'guardian'
                      AND NOT EXISTS (
                        SELECT 1 FROM storage_root_roles o JOIN identities oi ON oi.id = o.identity_id
                        WHERE o.root_id = r.root_id AND LOWER(o.role) = 'guardian' AND o.identity_id <> :id AND oi.is_active = 1
                      )
                    ORDER BY sr.root_path
                    """
                ),
        params,
    )


def set_subject_application_role_1(db: Session, params: Any) -> Any:
    """DELETE ir FROM identity_roles ir JOIN roles r ON r.id = ir.role_id WHERE ( (:identity_id IS NOT NULL AND ir.id"""
    return db.execute(
        text(
                    """
                    DELETE ir
                    FROM identity_roles ir
                    JOIN roles r ON r.id = ir.role_id
                    WHERE (
                        (:identity_id IS NOT NULL AND ir.identity_id = :identity_id)
                        OR
                        (:directory_group_id IS NOT NULL AND ir.directory_group_id = :directory_group_id)
                    )
                      AND r.code IN ('user', 'platform_admin')
                    """
                ),
        params,
    )


def set_subject_application_role_2(db: Session, params: Any) -> Any:
    """INSERT INTO identity_roles ( identity_id, directory_group_id, role_id, source, created_at ) VALUES ( :identity"""
    return db.execute(
        text(
                    """
                    INSERT INTO identity_roles (
                      identity_id,
                      directory_group_id,
                      role_id,
                      source,
                      created_at
                    ) VALUES (
                      :identity_id,
                      :directory_group_id,
                      :role_id,
                      'manual',
                      NOW()
                    )
                    """
                ),
        params,
    )


def list_identity_overview_1(db: Session) -> Any:
    """SELECT i.id, i.username, i.display_name, i.email, i.auth_source, i.external_id, i.source_id, i.is_active, i.ty"""
    return db.execute(
        text(
                        """
                        SELECT
                          i.id,
                          i.username,
                          i.display_name,
                          i.email,
                          i.auth_source,
                          i.external_id,
                          i.source_id,
                          i.is_active,
                          i.type,
                          i.snapshot_source,
                          COALESCE(i.provisioning_source, 'explicit') AS provisioning_source,
                          i.status,
                          i.created_at,
                          i.updated_at,
                          i.last_snapshot_at,
                          ids.name AS source_name
                        FROM identities i
                        LEFT JOIN identity_sources ids ON ids.id = i.source_id
                        WHERE LOWER(COALESCE(i.type, 'user')) = 'user'
                          AND LOWER(COALESCE(i.auth_source, '')) = 'local'
                        ORDER BY i.id DESC
                        LIMIT 500
                        """
                    ),
    )


def list_identity_overview_2(db: Session) -> Any:
    """SELECT i.id, i.username, i.display_name, i.email, i.auth_source, i.external_id, i.source_id, i.is_active, i.ty"""
    return db.execute(
        text(
                        """
                        SELECT
                          i.id,
                          i.username,
                          i.display_name,
                          i.email,
                          i.auth_source,
                          i.external_id,
                          i.source_id,
                          i.is_active,
                          i.type,
                          i.snapshot_source,
                          COALESCE(i.provisioning_source, 'explicit') AS provisioning_source,
                          i.status,
                          i.created_at,
                          i.updated_at,
                          i.last_snapshot_at,
                          ids.name AS source_name
                        FROM identities i
                        LEFT JOIN identity_sources ids ON ids.id = i.source_id
                        WHERE COALESCE(i.provisioning_source, 'explicit') <> 'legacy_auto_snapshot'
                        ORDER BY i.id DESC
                        LIMIT 500
                        """
                    ),
    )


def list_identity_overview_3(db: Session) -> Any:
    """SELECT dg.id, dg.external_id, dg.dn, dg.identity_source_id, dg.name AS display_name, dg.created_at, dg.updated"""
    return db.execute(
        text(
                        """
                        SELECT
                          dg.id,
                          dg.external_id,
                          dg.dn,
                          dg.identity_source_id,
                          dg.name AS display_name,
                          dg.created_at,
                          dg.updated_at,
                          dg.last_snapshot_at,
                          ids.name AS source_name,
                          (
                            SELECT COUNT(*)
                            FROM directory_group_members dgm
                            WHERE dgm.group_id = dg.id
                              AND dgm.deleted_at IS NULL
                          ) AS members_count
                        FROM directory_groups dg
                        LEFT JOIN identity_sources ids ON ids.id = dg.identity_source_id
                        WHERE dg.deleted_at IS NULL
                          AND EXISTS (
                            SELECT 1
                            FROM identity_roles ir
                            JOIN roles r ON r.id = ir.role_id
                            WHERE ir.directory_group_id = dg.id
                              AND r.code IN ('user', 'platform_admin')
                          )
                        ORDER BY dg.id DESC
                        LIMIT 500
                        """
                    ),
    )


def list_identity_overview_4(db: Session, params: Any) -> Any:
    """SELECT identity_id, role_code FROM v_identity_effective_roles WHERE identity_id IN :ids ORDER BY identity_id, """
    return db.execute(
        text(
                        """
                        SELECT identity_id, role_code
                        FROM v_identity_effective_roles
                        WHERE identity_id IN :ids
                        ORDER BY identity_id, role_code
                        """
                    ).bindparams(bindparam("ids", expanding=True)),
        params,
    )


def list_identity_overview_5(db: Session, params: Any) -> Any:
    """SELECT ir.directory_group_id, r.code AS role_code FROM identity_roles ir JOIN roles r ON r.id = ir.role_id WHE"""
    return db.execute(
        text(
                        """
                        SELECT ir.directory_group_id, r.code AS role_code
                        FROM identity_roles ir
                        JOIN roles r ON r.id = ir.role_id
                        WHERE ir.directory_group_id IN :ids
                        ORDER BY ir.directory_group_id, r.code
                        """
                    ).bindparams(bindparam("ids", expanding=True)),
        params,
    )


def create_identity_1(db: Session, params: Any) -> Any:
    """SELECT id FROM identities WHERE LOWER(COALESCE(username, '')) = LOWER(:username) AND LOWER(COALESCE(auth_sourc"""
    return db.execute(
        text(
                        """
                        SELECT id
                        FROM identities
                        WHERE LOWER(COALESCE(username, '')) = LOWER(:username)
                          AND LOWER(COALESCE(auth_source, '')) IN ('local', 'internal')
                        LIMIT 1
                        """
                    ),
        params,
    )


def create_identity_2(db: Session, params: Any) -> Any:
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
                          'local',
                          1,
                          1,
                          NULL,
                          'explicit',
                          'active',
                          NOW(),
                          NOW()
                        )
                        """
                    ),
        params,
    )


def create_identity_3(db: Session, params: Any) -> Any:
    """SELECT id, username, display_name, email, auth_source, external_id, source_id, is_active, type FROM identities"""
    return db.execute(
        text(
                        """
                        SELECT id, username, display_name, email, auth_source, external_id, source_id, is_active, type
                        FROM identities
                        WHERE source_id = :source_id
                          AND external_id = :external_id
                        LIMIT 1
                        """
                    ),
        params,
    )


def create_identity_4(db: Session, params: Any) -> Any:
    """INSERT INTO local_credentials ( identity_id, password_hash, password_version, last_rotated_at, created_at, upd"""
    return db.execute(
        text(
                        """
                        INSERT INTO local_credentials (
                          identity_id,
                          password_hash,
                          password_version,
                          last_rotated_at,
                          created_at,
                          updated_at,
                          deleted_at
                        ) VALUES (
                          :identity_id,
                          :password_hash,
                          'b2s$v=1$bcrypt',
                          NOW(),
                          NOW(),
                          NOW(),
                          NULL
                        )
                        """
                    ),
        params,
    )


def create_identity_5(db: Session, params: Any) -> Any:
    """SELECT id, username, display_name, email, auth_source, external_id, source_id, is_active, type FROM identities"""
    return db.execute(
        text(
                        """
                        SELECT id, username, display_name, email, auth_source, external_id, source_id, is_active, type
                        FROM identities
                        WHERE source_id = :source_id
                          AND external_id = :external_id
                        LIMIT 1
                        """
                    ),
        params,
    )


def create_identity_6(db: Session, params: Any) -> Any:
    """UPDATE identities SET username = :username, display_name = :display_name, email = :email, auth_source = 'ad', """
    return db.execute(
        text(
                            """
                            UPDATE identities
                            SET username = :username,
                                display_name = :display_name,
                                email = :email,
                                auth_source = 'ad',
                                is_active = 1,
                                snapshot_source = NULL,
                                provisioning_source = 'explicit',
                                status = 'active',
                                updated_at = NOW(6)
                            WHERE id = :id
                            """
                        ),
        params,
    )


def create_identity_7(db: Session, params: Any) -> Any:
    """SELECT id, username, display_name, email, auth_source, external_id, source_id, is_active, type FROM identities"""
    return db.execute(
        text(
                            """
                            SELECT id, username, display_name, email, auth_source, external_id, source_id, is_active, type
                            FROM identities
                            WHERE id = :id
                            LIMIT 1
                            """
                        ),
        params,
    )


def create_identity_8(db: Session, params: Any) -> Any:
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
                              1,
                              1,
                              NULL,
                              'explicit',
                              'active',
                              NOW(),
                              NOW()
                            )
                            """
                        ),
        params,
    )


def create_identity_9(db: Session, params: Any) -> Any:
    """SELECT id, username, display_name, email, auth_source, external_id, source_id, is_active, type FROM identities"""
    return db.execute(
        text(
                            """
                            SELECT id, username, display_name, email, auth_source, external_id, source_id, is_active, type
                            FROM identities
                            WHERE source_id = :source_id
                              AND external_id = :external_id
                            LIMIT 1
                            """
                        ),
        params,
    )


def create_identity_10(db: Session, params: Any) -> Any:
    """SELECT id, name, external_id, identity_source_id FROM directory_groups WHERE identity_source_id = :source_id A"""
    return db.execute(
        text(
                        """
                        SELECT id, name, external_id, identity_source_id
                        FROM directory_groups
                        WHERE identity_source_id = :source_id
                          AND external_id = :external_id
                          AND deleted_at IS NULL
                        LIMIT 1
                        """
                    ),
        params,
    )


def create_identity_11(db: Session, params: Any) -> Any:
    """UPDATE directory_groups SET name = :display_name, dn = :dn, snapshot_source = NULL, updated_at = NOW(6) WHERE """
    return db.execute(
        text(
                            """
                            UPDATE directory_groups
                            SET name = :display_name,
                                dn = :dn,
                                snapshot_source = NULL,
                                updated_at = NOW(6)
                            WHERE id = :id
                            """
                        ),
        params,
    )


def create_identity_12(db: Session, params: Any) -> Any:
    """INSERT INTO directory_groups ( identity_source_id, external_id, dn, name, snapshot_version, snapshot_source, s"""
    return db.execute(
        text(
                            """
                            INSERT INTO directory_groups (
                              identity_source_id,
                              external_id,
                              dn,
                              name,
                              snapshot_version,
                              snapshot_source,
                              snapshot_hash,
                              last_snapshot_at,
                              captured_at,
                              created_at,
                              updated_at,
                              deleted_at
                            ) VALUES (
                              :source_id,
                              :external_id,
                              :dn,
                              :display_name,
                              1,
                              NULL,
                              NULL,
                              NULL,
                              NOW(),
                              NOW(),
                              NOW(),
                              NULL
                            )
                            """
                        ),
        params,
    )


def create_identity_13(db: Session, params: Any) -> Any:
    """SELECT id, name, external_id, identity_source_id FROM directory_groups WHERE identity_source_id = :source_id A"""
    return db.execute(
        text(
                            """
                            SELECT id, name, external_id, identity_source_id
                            FROM directory_groups
                            WHERE identity_source_id = :source_id
                              AND external_id = :external_id
                              AND deleted_at IS NULL
                            LIMIT 1
                            """
                        ),
        params,
    )


def create_identity_14(db: Session, params: Any) -> Any:
    """SELECT dg.id, 'group' AS type, dg.name AS username, dg.name AS display_name, NULL AS email, 'ad' AS auth_sourc"""
    return db.execute(
        text(
                        """
                        SELECT
                          dg.id,
                          'group' AS type,
                          dg.name AS username,
                          dg.name AS display_name,
                          NULL AS email,
                          'ad' AS auth_source,
                          dg.external_id,
                          dg.identity_source_id AS source_id,
                          NULL AS is_active
                        FROM directory_groups dg
                        WHERE id = :id
                        LIMIT 1
                        """
                    ),
        params,
    )


def list_identity_group_members_1(db: Session, params: Any) -> Any:
    """SELECT du.id, du.username, du.display_name, du.email FROM directory_group_members dgm JOIN directory_users du """
    return db.execute(
        text(
                    """
                    SELECT
                      du.id,
                      du.username,
                      du.display_name,
                      du.email
                    FROM directory_group_members dgm
                    JOIN directory_users du ON du.id = dgm.directory_user_id
                    WHERE dgm.group_id = :group_id
                      AND dgm.deleted_at IS NULL
                    ORDER BY COALESCE(NULLIF(TRIM(du.display_name), ''), du.username, du.email, CAST(du.id AS CHAR))
                    LIMIT 500
                    """
                ),
        params,
    )


def delete_identity_1(db: Session, params: Any) -> Any:
    """SELECT dg.id, dg.name AS display_name, dg.external_id, dg.identity_source_id AS source_id, 'ad' AS auth_source"""
    return db.execute(
        text(
                        """
                        SELECT
                          dg.id,
                          dg.name AS display_name,
                          dg.external_id,
                          dg.identity_source_id AS source_id,
                          'ad' AS auth_source,
                          'group' AS type
                        FROM directory_groups dg
                        WHERE dg.id = :id
                          AND dg.deleted_at IS NULL
                        LIMIT 1
                        """
                    ),
        params,
    )


def delete_identity_2(db: Session, params: Any) -> Any:
    """DELETE FROM identity_roles WHERE directory_group_id = :id"""
    return db.execute(
        text(
                        """
                        DELETE FROM identity_roles
                        WHERE directory_group_id = :id
                        """
                    ),
        params,
    )


def delete_identity_3(db: Session, params: Any) -> Any:
    """SELECT i.id, i.username, i.display_name, i.auth_source, i.provisioning_source, i.type FROM identities i WHERE """
    return db.execute(
        text(
                    """
                    SELECT
                      i.id,
                      i.username,
                      i.display_name,
                      i.auth_source,
                      i.provisioning_source,
                      i.type
                    FROM identities i
                    WHERE i.id = :id
                    LIMIT 1
                    """
                ),
        params,
    )


def delete_identity_4(db: Session, params: Any) -> Any:
    """SELECT dg.id, dg.name AS display_name, dg.external_id, dg.identity_source_id AS source_id, 'ad' AS auth_source"""
    return db.execute(
        text(
                        """
                        SELECT
                          dg.id,
                          dg.name AS display_name,
                          dg.external_id,
                          dg.identity_source_id AS source_id,
                          'ad' AS auth_source,
                          'group' AS type
                        FROM directory_groups dg
                        WHERE dg.id = :id
                          AND dg.deleted_at IS NULL
                        LIMIT 1
                        """
                    ),
        params,
    )


def delete_identity_5(db: Session, params: Any) -> Any:
    """DELETE FROM identity_roles WHERE directory_group_id = :id"""
    return db.execute(
        text(
                            """
                            DELETE FROM identity_roles
                            WHERE directory_group_id = :id
                            """
                        ),
        params,
    )


def delete_identity_6(db: Session, params: Any) -> Any:
    """DELETE FROM identity_bindings WHERE identity_id = :id"""
    return db.execute(
        text(
                    """
                    DELETE FROM identity_bindings
                    WHERE identity_id = :id
                    """
                ),
        params,
    )


def delete_identity_7(db: Session, params: Any) -> Any:
    """DELETE FROM local_credentials WHERE identity_id = :id"""
    return db.execute(
        text(
                    """
                    DELETE FROM local_credentials
                    WHERE identity_id = :id
                    """
                ),
        params,
    )


def delete_identity_8(db: Session, params: Any) -> Any:
    """DELETE FROM identities WHERE id = :id"""
    return db.execute(
        text(
                    """
                    DELETE FROM identities
                    WHERE id = :id
                    """
                ),
        params,
    )


def update_identity_1(db: Session, params: Any) -> Any:
    """SELECT dg.id, dg.name AS display_name, NULL AS username, NULL AS is_active, 'group' AS type, 'ad' AS auth_sour"""
    return db.execute(
        text(
                        """
                        SELECT
                          dg.id,
                          dg.name AS display_name,
                          NULL AS username,
                          NULL AS is_active,
                          'group' AS type,
                          'ad' AS auth_source
                        FROM directory_groups dg
                        WHERE id = :id
                        LIMIT 1
                        """
                    ),
        params,
    )


def update_identity_2(db: Session, params: Any) -> Any:
    """SELECT id, username, display_name, is_active, type, auth_source FROM identities WHERE id = :id LIMIT 1"""
    return db.execute(
        text(
                        """
                        SELECT id, username, display_name, is_active, type, auth_source
                        FROM identities
                        WHERE id = :id
                        LIMIT 1
                        """
                    ),
        params,
    )


def update_identity_3(db: Session, params: Any) -> Any:
    """SELECT dg.id, 'group' AS type, dg.name AS username, dg.name AS display_name, NULL AS email, 'ad' AS auth_sourc"""
    return db.execute(
        text(
                        """
                        SELECT
                          dg.id,
                          'group' AS type,
                          dg.name AS username,
                          dg.name AS display_name,
                          NULL AS email,
                          'ad' AS auth_source,
                          dg.external_id,
                          dg.identity_source_id AS source_id,
                          NULL AS is_active
                        FROM directory_groups dg
                        WHERE id = :id
                        LIMIT 1
                        """
                    ),
        params,
    )


def update_identity_4(db: Session, params: Any) -> Any:
    """SELECT id, username, display_name, email, auth_source, external_id, source_id, is_active, type FROM identities"""
    return db.execute(
        text(
                        """
                        SELECT id, username, display_name, email, auth_source, external_id, source_id, is_active, type
                        FROM identities
                        WHERE id = :id
                        LIMIT 1
                        """
                    ),
        params,
    )


def hand_over_guardianship_1(db: Session, params: Any) -> Any:
    """SELECT id, is_active, type FROM identities WHERE id = :id"""
    return db.execute(
        text("SELECT id, is_active, type FROM identities WHERE id = :id"),
        params,
    )


def hand_over_guardianship_2(db: Session, params: Any) -> Any:
    """SELECT root_id FROM storage_root_roles WHERE identity_id = :id AND LOWER(role) = 'guardian'"""
    return db.execute(
        text("SELECT root_id FROM storage_root_roles WHERE identity_id = :id AND LOWER(role) = 'guardian'"),
        params,
    )


def hand_over_guardianship_3(db: Session, params: Any) -> Any:
    """SELECT 1 FROM storage_root_roles WHERE root_id = :root AND identity_id = :to AND LOWER(role) = 'guardian'"""
    return db.execute(
        text("SELECT 1 FROM storage_root_roles WHERE root_id = :root AND identity_id = :to AND LOWER(role) = 'guardian'"),
        params,
    )


def hand_over_guardianship_4(db: Session, params: Any) -> Any:
    """INSERT INTO storage_root_roles (root_id, identity_id, role, assigned_by, assigned_at) VALUES (:root, :to, 'gua"""
    return db.execute(
        text("INSERT INTO storage_root_roles (root_id, identity_id, role, assigned_by, assigned_at) VALUES (:root, :to, 'guardian', :by, NOW())"),
        params,
    )


def hand_over_guardianship_5(db: Session, params: Any) -> Any:
    """DELETE FROM storage_root_roles WHERE identity_id = :id AND LOWER(role) = 'guardian' AND root_id IN :roots"""
    return db.execute(
        text("DELETE FROM storage_root_roles WHERE identity_id = :id AND LOWER(role) = 'guardian' AND root_id IN :roots")
                    .bindparams(bindparam("roots", expanding=True)),
        params,
    )


def create_substitute_1(db: Session, params: Any) -> Any:
    """SELECT id FROM identities WHERE id = :id"""
    return db.execute(
        text("SELECT id FROM identities WHERE id = :id"),
        params,
    )


def create_substitute_2(db: Session, params: Any) -> Any:
    """SELECT 1 FROM storage_root_roles WHERE identity_id = :id AND LOWER(role) = 'guardian' LIMIT 1"""
    return db.execute(
        text("SELECT 1 FROM storage_root_roles WHERE identity_id = :id AND LOWER(role) = 'guardian' LIMIT 1"),
        params,
    )


def create_substitute_3(db: Session, params: Any) -> Any:
    """SELECT id, is_active, type FROM identities WHERE id = :id"""
    return db.execute(
        text("SELECT id, is_active, type FROM identities WHERE id = :id"),
        params,
    )


def create_substitute_4(db: Session, params: Any) -> Any:
    """SELECT 1 FROM guardian_substitutes WHERE identity_id = :id AND revoked_at IS NULL AND starts_at < :ends AND en"""
    return db.execute(
        text(
                    """
                    SELECT 1 FROM guardian_substitutes WHERE identity_id = :id AND revoked_at IS NULL
                      AND starts_at < :ends AND ends_at > :starts LIMIT 1
                    """
                ),
        params,
    )


def create_substitute_5(db: Session, params: Any) -> Any:
    """INSERT INTO guardian_substitutes (identity_id, substitute_identity_id, starts_at, ends_at, reason, created_by)"""
    return db.execute(
        text(
                    """
                    INSERT INTO guardian_substitutes (identity_id, substitute_identity_id, starts_at, ends_at, reason, created_by)
                    VALUES (:id, :sub, :starts, :ends, :reason, :by)
                    """
                ),
        params,
    )


def revoke_substitute_1(db: Session, params: Any) -> Any:
    """SELECT identity_id FROM guardian_substitutes WHERE id = :id AND revoked_at IS NULL"""
    return db.execute(
        text("SELECT identity_id FROM guardian_substitutes WHERE id = :id AND revoked_at IS NULL"),
        params,
    )


def revoke_substitute_2(db: Session, params: Any) -> Any:
    """UPDATE guardian_substitutes SET revoked_at = UTC_TIMESTAMP(), revoked_by = :by WHERE id = :id"""
    return db.execute(
        text("UPDATE guardian_substitutes SET revoked_at = UTC_TIMESTAMP(), revoked_by = :by WHERE id = :id"),
        params,
    )


def list_guardian_counts_1(db: Session) -> Any:
    """SELECT r.identity_id, COUNT(*) AS folders, SUM(NOT EXISTS (SELECT 1 FROM storage_root_roles o WHERE o.root_id """
    return db.execute(
        text(
                    """
                    SELECT r.identity_id, COUNT(*) AS folders,
                      SUM(NOT EXISTS (SELECT 1 FROM storage_root_roles o WHERE o.root_id = r.root_id AND LOWER(o.role) = 'guardian'
                                      AND o.identity_id <> r.identity_id)) AS sole
                    FROM storage_root_roles r WHERE LOWER(r.role) = 'guardian' AND r.identity_id IS NOT NULL
                    GROUP BY r.identity_id
                    """
                ),
    )


def list_platform_admins_1(db: Session) -> Any:
    """SELECT i.id, i.username, COALESCE(NULLIF(i.display_name, ''), i.username) AS name, i.email, i.auth_source, i.i"""
    return db.execute(
        text(
                    """
                    SELECT i.id, i.username, COALESCE(NULLIF(i.display_name, ''), i.username) AS name, i.email, i.auth_source,
                      i.is_active, s.name AS source_name
                    FROM identity_roles ir JOIN roles r ON r.id = ir.role_id AND r.code = 'platform_admin'
                    JOIN identities i ON i.id = ir.identity_id LEFT JOIN identity_sources s ON s.id = i.source_id
                    WHERE ir.identity_id IS NOT NULL ORDER BY i.auth_source DESC, name
                    """
                ),
    )


def list_platform_admins_2(db: Session) -> Any:
    """SELECT g.id, g.name, g.dn, s.name AS source_name FROM identity_roles ir JOIN roles r ON r.id = ir.role_id AND """
    return db.execute(
        text(
                    """
                    SELECT g.id, g.name, g.dn, s.name AS source_name
                    FROM identity_roles ir JOIN roles r ON r.id = ir.role_id AND r.code = 'platform_admin'
                    JOIN directory_groups g ON g.id = ir.directory_group_id LEFT JOIN identity_sources s ON s.id = g.identity_source_id
                    WHERE ir.directory_group_id IS NOT NULL ORDER BY g.name
                    """
                ),
    )


def list_platform_admins_3(db: Session, params: Any) -> Any:
    """SELECT DISTINCT i.id, i.username, COALESCE(NULLIF(i.display_name, ''), i.username) AS name, i.is_active FROM d"""
    return db.execute(
        text(
                        """
                        SELECT DISTINCT i.id, i.username, COALESCE(NULLIF(i.display_name, ''), i.username) AS name, i.is_active
                        FROM directory_effective_memberships dem
                        JOIN identity_bindings ib ON ib.directory_user_id = dem.directory_user_id AND ib.deleted_at IS NULL
                        JOIN identities i ON i.id = ib.identity_id
                        WHERE dem.directory_group_id = :gid ORDER BY name
                        """
                    ),
        params,
    )


def list_platform_admins_4(db: Session, params: Any) -> Any:
    """SELECT COUNT(DISTINCT directory_user_id) FROM directory_effective_memberships WHERE directory_group_id = :gid"""
    return db.execute(
        text("SELECT COUNT(DISTINCT directory_user_id) FROM directory_effective_memberships WHERE directory_group_id = :gid"),
        params,
    )


def list_platform_admins_5(db: Session) -> Any:
    """SELECT COUNT(DISTINCT v.identity_id) FROM v_identity_effective_roles v JOIN identities i ON i.id = v.identity_"""
    return db.execute(
        text(
                    "SELECT COUNT(DISTINCT v.identity_id) FROM v_identity_effective_roles v JOIN identities i ON i.id = v.identity_id"
                    " WHERE v.role_code = 'platform_admin' AND i.is_active = 1"
                ),
    )


def get_identity_overview_1(db: Session, params: Any) -> Any:
    """SELECT i.id, i.type, i.username, i.display_name, i.email, i.auth_source, i.external_id, i.is_active, i.status,"""
    return db.execute(
        text(
                    """
                    SELECT i.id, i.type, i.username, i.display_name, i.email, i.auth_source, i.external_id, i.is_active, i.status,
                      i.created_at, i.updated_at, i.source_id, s.name AS source_name,
                      (SELECT du.dn FROM directory_users du WHERE du.identity_source_id = i.source_id
                         AND (du.external_id = i.external_id OR LOWER(du.username) = LOWER(i.username)) ORDER BY du.id DESC LIMIT 1) AS dn
                    FROM identities i LEFT JOIN identity_sources s ON s.id = i.source_id
                    WHERE i.id = :id
                    """
                ),
        params,
    )


def get_identity_overview_2(db: Session, params: Any) -> Any:
    """SELECT DISTINCT role_code AS code, via FROM v_identity_effective_roles WHERE identity_id = :id"""
    return db.execute(
        text("SELECT DISTINCT role_code AS code, via FROM v_identity_effective_roles WHERE identity_id = :id"),
        params,
    )


def get_identity_overview_3(db: Session, params: Any) -> Any:
    """SELECT sr.id, sr.name, sr.root_path, (SELECT GROUP_CONCAT(COALESCE(NULLIF(o.display_name, ''), o.username) ORD"""
    return db.execute(
        text(
                    """
                    SELECT sr.id, sr.name, sr.root_path,
                      (SELECT GROUP_CONCAT(COALESCE(NULLIF(o.display_name, ''), o.username) ORDER BY o.username SEPARATOR '|')
                         FROM storage_root_roles x JOIN identities o ON o.id = x.identity_id
                         WHERE x.root_id = sr.id AND LOWER(x.role) = 'guardian' AND x.identity_id <> :id) AS others,
                      (SELECT GROUP_CONCAT(x.identity_id) FROM storage_root_roles x
                         WHERE x.root_id = sr.id AND LOWER(x.role) = 'guardian' AND x.identity_id <> :id) AS other_ids
                    FROM storage_root_roles r JOIN storage_roots sr ON sr.id = r.root_id
                    WHERE r.identity_id = :id AND LOWER(r.role) = 'guardian'
                    ORDER BY sr.root_path
                    """
                ),
        params,
    )


def get_identity_overview_4(db: Session, params: Any) -> Any:
    """SELECT id, email FROM identities WHERE id IN :ids"""
    return db.execute(
        text("SELECT id, email FROM identities WHERE id IN :ids").bindparams(bindparam("ids", expanding=True)),
        params,
    )


def get_identity_overview_5(db: Session, params: Any) -> Any:
    """SELECT LOWER(status), COUNT(*) FROM access_requests WHERE requester_identity_id = :id GROUP BY LOWER(status)"""
    return db.execute(
        text("SELECT LOWER(status), COUNT(*) FROM access_requests WHERE requester_identity_id = :id GROUP BY LOWER(status)"),
        params,
    )
