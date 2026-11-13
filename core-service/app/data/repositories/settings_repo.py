"""Advanced settings (one JSON document, row id 1) and what the guided setup needs to resume at the right step."""
from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def read_payload_raw(db: Session) -> Any:
    row = db.execute(text("SELECT payload_json FROM advanced_settings_config WHERE id = 1")).mappings().first()
    return row.get("payload_json") if row else None


def write_payload_raw(db: Session, payload_json: str) -> None:
    db.execute(text("""INSERT INTO advanced_settings_config (id, payload_json) VALUES (1, :payload)
                       ON DUPLICATE KEY UPDATE payload_json = :payload, updated_at = CURRENT_TIMESTAMP"""), {"payload": payload_json})
    db.commit()


def _first(db: Session, sql: str, params: dict | None = None) -> dict | None:
    row = db.execute(text(sql), params or {}).mappings().first()
    return dict(row) if row else None


def setup_snapshot(db: Session) -> dict[str, Any]:
    """What is configured already: folders governed, the first zone, directory, file server, group OU, imported groups."""
    zone = _first(db, "SELECT id, name, code, description FROM zones ORDER BY id LIMIT 1")
    return {
        "roots": int(db.execute(text("SELECT COUNT(*) FROM storage_roots")).scalar() or 0),
        "zone": zone,
        "directory": _first(db, """SELECT id, name, directory_flavor, protocol, host, port, domain_name, base_dn, bind_dn,
                                          bind_password_ref, tls_verify, tls_ca_pem, tls_server_name
                                   FROM identity_sources WHERE LOWER(type) = 'ad' AND is_active = 1 ORDER BY id LIMIT 1"""),
        "server": _first(db, "SELECT id, name, host, port, bind_dn, bind_password_ref FROM storage_endpoints ORDER BY id LIMIT 1"),
        "policy": _first(db, "SELECT static_ou_dn FROM zone_provisioning_policy WHERE zone_id = :zone", {"zone": int(zone["id"])}) if zone else None,
        "imported_groups": int(db.execute(text("SELECT COUNT(DISTINCT directory_group_id) FROM identity_roles WHERE directory_group_id IS NOT NULL")).scalar() or 0),
    }
