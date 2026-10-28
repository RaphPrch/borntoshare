"""SSO providers (Keycloak) and the access decision at an SSO sign-in.

Access at the first SSO sign-in:
1. identity already created by this provider (same subject): its roles follow the token at every sign-in
2. otherwise, with « link existing identities »: an active AD identity with the same user name is used
   (its roles come from BornToShare: direct roles and AD groups)
3. otherwise: an identity is created when the token carries a mapped role (or a default role is set)
Nothing matches: the sign-in is refused. A provider-created identity whose roles disappeared is refused too.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

PUBLIC_FIELDS = (
    "id", "identity_source_id", "name", "base_url", "realm", "client_id", "scopes", "username_claim", "roles_claim",
    "default_role", "link_existing_identities", "button_label", "verify_tls", "is_enabled", "status", "last_check_at", "last_message",
)


def _json(value: Any) -> Any:
    if isinstance(value, (str, bytes)) and value:
        try:
            return json.loads(value)
        except ValueError:
            return None
    return value


def provider_public(row: dict[str, Any]) -> dict[str, Any]:
    out = {k: row.get(k) for k in PUBLIC_FIELDS}
    for key in ("link_existing_identities", "verify_tls", "is_enabled"):
        out[key] = bool(out[key])
    out["role_mapping"] = _json(row.get("role_mapping_json")) or []
    out["has_client_secret"] = bool(row.get("client_secret_ref"))
    out["issuer_hint"] = f"{str(row.get('base_url') or '').rstrip('/')}/realms/{row.get('realm')}"
    if out.get("last_check_at") is not None:
        out["last_check_at"] = out["last_check_at"].isoformat() + "Z"
    return out


def get_provider_row(db: Session, provider_id: int) -> dict[str, Any] | None:
    row = db.execute(text("SELECT * FROM sso_providers WHERE id = :id"), {"id": int(provider_id)}).mappings().first()
    return dict(row) if row else None


def list_providers(db: Session) -> list[dict[str, Any]]:
    return [provider_public(dict(r)) for r in db.execute(text("SELECT * FROM sso_providers ORDER BY name")).mappings()]


def _sync_identity_source(db: Session, provider: dict[str, Any]) -> int:
    """Identity source of type oidc owning the identities created by this provider."""
    issuer = f"{str(provider['base_url']).rstrip('/')}/realms/{provider['realm']}"
    params = {
        "name": f"SSO · {provider['name']}"[:190],
        "issuer": issuer,
        "client_id": provider["client_id"],
        "active": 1 if provider.get("is_enabled") else 0,
        "status": "active" if provider.get("is_enabled") else "disabled",
    }
    if provider.get("identity_source_id"):
        db.execute(
            text(
                """
                UPDATE identity_sources SET name = :name, issuer_url = :issuer, external_id = :client_id,
                  is_active = :active, status = :status
                WHERE id = :id
                """
            ),
            {**params, "id": int(provider["identity_source_id"])},
        )
        return int(provider["identity_source_id"])
    result = db.execute(
        text(
            """
            INSERT INTO identity_sources (type, name, issuer_url, external_id, capabilities, auth_enabled, is_active, status)
            VALUES ('oidc', :name, :issuer, :client_id, JSON_OBJECT('sso', TRUE), 0, :active, :status)
            """
        ),
        params,
    )
    return int(result.lastrowid)


def save_provider(db: Session, data: dict[str, Any], provider_id: int | None = None) -> dict[str, Any]:
    """Create or update; the caller commits. A missing client_secret_ref keeps the stored one."""
    fields = {
        "name": data["name"].strip(),
        "base_url": data["base_url"].strip().rstrip("/"),
        "realm": data["realm"].strip(),
        "client_id": data["client_id"].strip(),
        "scopes": (data.get("scopes") or "openid profile email").strip(),
        "username_claim": (data.get("username_claim") or "preferred_username").strip(),
        "roles_claim": (data.get("roles_claim") or "realm_access.roles").strip(),
        "role_mapping_json": json.dumps(
            [{"value": str(m["value"]).strip(), "role": str(m["role"]).strip()} for m in data.get("role_mapping") or [] if str(m.get("value") or "").strip()]
        ),
        "default_role": (data.get("default_role") or None),
        "link_existing_identities": 1 if data.get("link_existing_identities", True) else 0,
        "button_label": (data.get("button_label") or "").strip() or None,
        "verify_tls": 1 if data.get("verify_tls", True) else 0,
        "is_enabled": 1 if data.get("is_enabled", True) else 0,
    }
    if data.get("client_secret_ref"):
        fields["client_secret_ref"] = data["client_secret_ref"]
    if data.get("public_client"):
        fields["client_secret_ref"] = None
    if provider_id is None:
        columns = ", ".join(fields)
        values = ", ".join(f":{k}" for k in fields)
        provider_id = int(db.execute(text(f"INSERT INTO sso_providers ({columns}) VALUES ({values})"), fields).lastrowid)
    else:
        assignments = ", ".join(f"{k} = :{k}" for k in fields)
        db.execute(text(f"UPDATE sso_providers SET {assignments} WHERE id = :id"), {**fields, "id": int(provider_id)})
    row = get_provider_row(db, provider_id) or {}
    source_id = _sync_identity_source(db, row)
    db.execute(text("UPDATE sso_providers SET identity_source_id = :sid WHERE id = :id"), {"sid": source_id, "id": provider_id})
    return provider_public(get_provider_row(db, provider_id) or {})


def delete_provider(db: Session, provider_id: int) -> None:
    """The identity source is disabled, not deleted: identities and their history stay."""
    row = get_provider_row(db, provider_id)
    if not row:
        return
    db.execute(text("DELETE FROM sso_providers WHERE id = :id"), {"id": int(provider_id)})
    if row.get("identity_source_id"):
        db.execute(
            text("UPDATE identity_sources SET is_active = 0, status = 'disabled' WHERE id = :id"),
            {"id": int(row["identity_source_id"])},
        )
        db.execute(
            text("UPDATE identities SET is_active = 0, status = 'inactive' WHERE source_id = :id AND auth_source = 'oidc'"),
            {"id": int(row["identity_source_id"])},
        )


# ============================================================
# Access decision
# ============================================================


def mapped_roles(provider: dict[str, Any], token_values: list[str]) -> list[str]:
    """BornToShare roles from the token values (Keycloak roles or groups) through the mapping, else the default."""
    mapping = _json(provider.get("role_mapping_json")) or []
    values = {str(v).strip().lower().lstrip("/") for v in token_values if str(v).strip()}
    roles = sorted({m["role"] for m in mapping if str(m.get("value") or "").strip().lower().lstrip("/") in values})
    if not roles and provider.get("default_role"):
        roles = [str(provider["default_role"])]
    return roles


def _role_ids(db: Session, codes: list[str]) -> dict[str, int]:
    if not codes:
        return {}
    rows = db.execute(text("SELECT id, code FROM roles")).mappings()
    return {r["code"]: int(r["id"]) for r in rows if r["code"] in codes}


def _sync_sso_roles(db: Session, identity_id: int, codes: list[str]) -> None:
    """Roles granted by the provider (source 'sso') follow the token; roles granted by hand stay."""
    db.execute(text("DELETE FROM identity_roles WHERE identity_id = :id AND source = 'sso'"), {"id": identity_id})
    for code, role_id in _role_ids(db, codes).items():
        db.execute(
            text("INSERT INTO identity_roles (identity_id, role_id, source) VALUES (:id, :role_id, 'sso')"),
            {"id": identity_id, "role_id": role_id},
        )


def resolve_sso_identity(db: Session, *, provider_id: int, claims: dict[str, Any]) -> dict[str, Any]:
    """Identity to open the session for, or a refusal reason. The caller commits."""
    provider = get_provider_row(db, provider_id)
    if not provider or not provider.get("is_enabled"):
        return {"found": False, "reason_code": "PROVIDER_DISABLED"}
    subject = str(claims.get("sub") or "").strip()
    username = str(claims.get("username") or "").strip()
    if not subject or not username:
        return {"found": False, "reason_code": "MISSING_CLAIMS"}
    roles = mapped_roles(provider, list(claims.get("roles") or []))
    source_id = int(provider["identity_source_id"])

    existing = db.execute(
        text("SELECT id, is_active, status FROM identities WHERE source_id = :sid AND external_id = :sub"),
        {"sid": source_id, "sub": subject},
    ).mappings().first()
    if existing:
        if not roles:
            return {"found": False, "reason_code": "NOT_ENTITLED"}
        db.execute(
            text("UPDATE identities SET username = :u, display_name = :d, email = :e, updated_at = NOW() WHERE id = :id"),
            {"u": username, "d": claims.get("name") or username, "e": claims.get("email"), "id": int(existing["id"])},
        )
        _sync_sso_roles(db, int(existing["id"]), roles)
        return {"found": True, "identity_id": int(existing["id"]), "is_active": bool(existing["is_active"]), "linked": "sso", "roles": roles}

    if provider.get("link_existing_identities"):
        ad = db.execute(
            text(
                """
                SELECT i.id, i.is_active FROM identities i
                JOIN identity_sources s ON s.id = i.source_id
                WHERE LOWER(i.auth_source) = 'ad' AND LOWER(COALESCE(i.type, 'user')) = 'user'
                  AND s.is_active = 1
                  AND (LOWER(i.username) = LOWER(:u) OR (:e <> '' AND LOWER(COALESCE(i.email, '')) = LOWER(:e)))
                ORDER BY i.is_active DESC, i.id
                LIMIT 1
                """
            ),
            {"u": username, "e": str(claims.get("email") or "")},
        ).mappings().first()
        if ad:
            return {"found": True, "identity_id": int(ad["id"]), "is_active": bool(ad["is_active"]), "linked": "ad"}

    if not roles:
        return {"found": False, "reason_code": "NOT_ENTITLED"}
    created = db.execute(
        text(
            """
            INSERT INTO identities (source_id, username, type, external_id, display_name, email, auth_source,
                                    is_active, provisioning_source, status)
            VALUES (:sid, :u, 'user', :sub, :d, :e, 'oidc', 1, 'sso', 'active')
            """
        ),
        {"sid": source_id, "u": username, "sub": subject, "d": claims.get("name") or username, "e": claims.get("email")},
    )
    identity_id = int(created.lastrowid)
    _sync_sso_roles(db, identity_id, roles)
    return {"found": True, "identity_id": identity_id, "is_active": True, "linked": "created", "roles": roles}
