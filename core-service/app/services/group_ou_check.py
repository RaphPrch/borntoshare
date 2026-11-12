"""The OU where an access group gets created must be delegated to the provisioning account, or the approval fails
once AD refuses (after the guardian said yes). Known before: the health check reads, for each OU in use, whether the
account may create groups there; a refused creation says it too. The newest of the two decides."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

DENIED_CODES = {"OU_NOT_DELEGATED", "OU_NOT_FOUND"}
DENIED_JOB_CODES = {"AD_GROUP_CREATE_DENIED", "AD_TARGET_OU_NOT_FOUND"}


def component_key(source_id: int, ou_dn: str) -> str:
    return f"group_ou:{int(source_id)}:{hashlib.sha1(ou_dn.strip().lower().encode()).hexdigest()[:12]}"


def ous_in_use(db: Session) -> dict[int, set[str]]:
    """identity source → the group OUs its folders would create groups in."""
    from app.api.provisioning_internal import get_storage_root_provisioning_context

    out: dict[int, set[str]] = {}
    for (root_id,) in db.execute(text("SELECT id FROM storage_roots WHERE deleted_at IS NULL")).all():
        try:
            ctx = get_storage_root_provisioning_context(int(root_id), db)
        except Exception:
            continue
        ou = ctx.get("effective_group_ou_dn") or ctx.get("zone_default_group_ou_dn") or ctx.get("default_group_ou_dn")
        if ctx.get("identity_source_id") and ou:
            out.setdefault(int(ctx["identity_source_id"]), set()).add(str(ou).strip())
    return out


def ou_targets(db: Session) -> list[dict[str, Any]]:
    from app.services.identity_source_accounts import load_accounts

    targets: list[dict[str, Any]] = []
    used = ous_in_use(db)
    for row in db.execute(text("""
            SELECT id, name, host, port, protocol, bind_dn, bind_password_ref, tls_verify, tls_ca_pem, tls_server_name
            FROM identity_sources WHERE is_active = 1 AND LOWER(type) = 'ad' AND host IS NOT NULL""")).mappings():
        account = load_accounts(db, int(row["id"])).get("provisioning") or {}
        bind_dn = account.get("bind_dn") or row["bind_dn"]
        secret_ref = account.get("bind_password_ref") or row["bind_password_ref"]
        if not bind_dn or not secret_ref:
            continue
        use_ssl = str(row["protocol"] or "").lower() != "ldap"
        port = int(row["port"] or (636 if use_ssl else 389))
        for ou in sorted(used.get(int(row["id"]), set())):
            targets.append({
                "component": component_key(int(row["id"]), ou), "label": f"Group OU · {ou}", "category": "directory",
                "kind": "ldap_ou", "target": f"{row['host']}:{port}", "ou_dn": ou, "use_ssl": use_ssl,
                "verify_tls": bool(row["tls_verify"]), "tls_ca_pem": row["tls_ca_pem"], "tls_server_name": row["tls_server_name"],
                "bind_dn": bind_dn, "secret_ref": secret_ref,
            })
    return targets


def _when(value: Any) -> datetime:
    return value if isinstance(value, datetime) else datetime.min


def verdict(db: Session, source_id: int | None, ou_dn: str | None) -> dict[str, Any]:
    """{"denied": bool, "message": str | None}: the newest evidence about creating groups in this OU."""
    if not source_id or not ou_dn:
        return {"denied": False, "message": None}
    try:
        check = db.execute(text("SELECT status, message, details_json, checked_at FROM infra_component_status WHERE component = :key"),
                           {"key": component_key(int(source_id), ou_dn)}).mappings().first()
        job = db.execute(text("""
            SELECT status, error_code, finished_at FROM provisioning_jobs
            WHERE action = 'grant_ad_access' AND status IN ('SUCCEEDED', 'FAILED')
              AND LOWER(JSON_VALUE(payload_json, '$.payload.target_ou_dn')) = :ou
            ORDER BY id DESC LIMIT 1"""), {"ou": ou_dn.strip().lower()}).mappings().first()
    except Exception:
        db.rollback()
        return {"denied": False, "message": None}
    evidence: list[tuple[datetime, bool, str]] = []
    if check:
        details = check["details_json"]
        details = json.loads(details) if isinstance(details, str) else (details or {})
        code = str(details.get("code") or "")
        if code in DENIED_CODES or code == "OU_DELEGATED":
            evidence.append((_when(check["checked_at"]), code in DENIED_CODES,
                             "L'unité d'organisation n'existe pas dans l'annuaire." if code == "OU_NOT_FOUND"
                             else "Le compte de provisioning n'a pas le droit de créer des groupes dans cette unité d'organisation."))
    if job and str(job["status"]).upper() == "FAILED" and str(job["error_code"] or "") in DENIED_JOB_CODES:
        evidence.append((_when(job["finished_at"]), True, "La dernière création de groupe dans cette unité d'organisation a été refusée par l'annuaire."))
    if not evidence:
        return {"denied": False, "message": None}
    _at, denied, message = max(evidence, key=lambda item: item[0])
    if not denied:
        return {"denied": False, "message": None}
    return {"denied": True, "message": f"{message} ({ou_dn}) Déléguez-la au compte, ou choisissez l'OU des groupes de la zone."}
