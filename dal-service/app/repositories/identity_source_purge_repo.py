from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session


def purge_identity_source_related_records(db: Session, source_id: int) -> None:
    """Delete every record tied to an identity source, children first (FK order)."""
    source_key = int(source_id or 0)
    if source_key <= 0:
        return

    statements = [
        """
        DELETE arie
        FROM access_request_item_executions arie
        JOIN access_requests ar
          ON ar.id = arie.access_request_id
        JOIN identities i
          ON i.id = ar.requester_identity_id
        WHERE i.source_id = :source_id
        """,
        """
        DELETE ari
        FROM access_request_items ari
        JOIN access_requests ar
          ON ar.id = ari.access_request_id
        JOIN identities i
          ON i.id = ar.requester_identity_id
        WHERE i.source_id = :source_id
        """,
        """
        DELETE ar
        FROM access_requests ar
        JOIN identities i
          ON i.id = ar.requester_identity_id
        WHERE i.source_id = :source_id
        """,
        """
        DELETE sr
        FROM storage_root_roles sr
        JOIN identities i
          ON i.id = sr.identity_id
        WHERE i.source_id = :source_id
        """,
        """
        DELETE ir
        FROM identity_roles ir
        LEFT JOIN identities i
          ON i.id = ir.identity_id
        LEFT JOIN directory_groups dg
          ON dg.id = ir.directory_group_id
        WHERE i.source_id = :source_id
           OR dg.identity_source_id = :source_id
        """,
        """
        DELETE lc
        FROM local_credentials lc
        JOIN identities i
          ON i.id = lc.identity_id
        WHERE i.source_id = :source_id
        """,
        """
        DELETE ib
        FROM identity_bindings ib
        LEFT JOIN identities i
          ON i.id = ib.identity_id
        LEFT JOIN directory_users du
          ON du.id = ib.directory_user_id
        WHERE i.source_id = :source_id
           OR du.identity_source_id = :source_id
        """,
        """
        DELETE dem
        FROM directory_effective_memberships dem
        LEFT JOIN directory_users du
          ON du.id = dem.directory_user_id
        LEFT JOIN directory_groups dg
          ON dg.id = dem.directory_group_id
        WHERE dem.identity_source_id = :source_id
           OR du.identity_source_id = :source_id
           OR dg.identity_source_id = :source_id
           OR dem.snapshot_id IN (
             SELECT ds.id
             FROM directory_snapshots ds
             WHERE ds.identity_source_id = :source_id
           )
        """,
        """
        DELETE dsm
        FROM directory_snapshot_memberships dsm
        JOIN directory_snapshots ds
          ON ds.id = dsm.snapshot_id
        WHERE ds.identity_source_id = :source_id
        """,
        """
        DELETE dsg
        FROM directory_snapshot_groups dsg
        JOIN directory_snapshots ds
          ON ds.id = dsg.snapshot_id
        WHERE ds.identity_source_id = :source_id
        """,
        """
        DELETE dsu
        FROM directory_snapshot_users dsu
        JOIN directory_snapshots ds
          ON ds.id = dsu.snapshot_id
        WHERE ds.identity_source_id = :source_id
        """,
        """
        DELETE dgm
        FROM directory_group_members dgm
        LEFT JOIN directory_groups dg
          ON dg.id = dgm.group_id
        LEFT JOIN directory_users du
          ON du.id = dgm.directory_user_id
        WHERE dg.identity_source_id = :source_id
           OR du.identity_source_id = :source_id
        """,
        """
        DELETE FROM directory_snapshots
        WHERE identity_source_id = :source_id
        """,
        """
        DELETE FROM directory_ous
        WHERE identity_source_id = :source_id
        """,
        """
        DELETE FROM directory_groups
        WHERE identity_source_id = :source_id
        """,
        """
        DELETE FROM directory_users
        WHERE identity_source_id = :source_id
        """,
        """
        DELETE FROM identities
        WHERE source_id = :source_id
        """,
    ]
    for statement in statements:
        db.execute(text(statement), {"source_id": source_key})
