from __future__ import annotations

import pytest
from starlette.requests import Request

from app.core import errors
from app.services import activity_log, audit_logger


@pytest.mark.parametrize(
    "value,expected",
    [("success", "success"), ("denied", "denied"), ("blocked", "denied"), ("error", "failure"), ("started", "in_progress"), ("nimporte", "failure")],
)
def test_an_unplanned_outcome_is_never_a_success(value, expected) -> None:
    assert audit_logger._normalize_result(value) == expected


def _request(method: str, path: str) -> Request:
    return Request({"type": "http", "method": method, "path": path, "headers": [(b"x-identity-id", b"7")], "query_string": b"", "server": ("x", 80), "scheme": "http"})


def test_a_refused_change_is_logged_but_not_a_read_nor_an_internal_call(monkeypatch) -> None:
    rows: list[dict] = []
    monkeypatch.setattr(activity_log, "log_activity", lambda db, **kwargs: rows.append(kwargs))

    errors._log_refusal(_request("POST", "/api/zones"), 409, "ZONE_EXISTS", "dup")
    assert rows[0]["action"] == "request.refused" and rows[0]["outcome"] == "failure" and rows[0]["actor_id"] == 7

    errors._log_refusal(_request("DELETE", "/api/x"), 403, "NO", "no")
    assert rows[1]["outcome"] == "denied"

    errors._log_refusal(_request("GET", "/api/zones"), 403, "NO", "no")
    errors._log_refusal(_request("POST", "/api/internal/jobs"), 409, "NO", "no")
    errors._log_refusal(_request("POST", "/api/zones"), 404, "NO", "no")
    assert len(rows) == 2


@pytest.mark.parametrize(
    "dn,valid",
    [
        ("OU=B2S Groups,OU=CORP,DC=CORP,DC=LOCAL", True),
        ("ou=b2s,dc=example,dc=test", True),
        ("CN=Dupont\\, Jean,DC=x", True),
        ("pas-un-dn", False),
        ("OU=", False),
        ("OU=x,,DC=y", False),
    ],
)
def test_organizational_units_must_be_dns(dn, valid) -> None:
    from app.api.zones import _DN

    assert bool(_DN.match(dn)) is valid


def test_zone_codes_are_checked() -> None:
    from app.schemas.zone import ZoneCreate

    assert ZoneCreate(name="Paris", code="PAR-1").code == "PAR-1"
    assert ZoneCreate(name="Paris", code=" ").code is None
    with pytest.raises(ValueError):
        ZoneCreate(name="Paris", code="a b$")


def test_the_wizard_creates_the_integrity_rules() -> None:
    from pathlib import Path

    schema = Path("/wizard-ui/backend/app/sql/schema")
    if not schema.is_dir():
        pytest.skip("wizard sources not mounted")
    core = {name: (schema / name).read_text(encoding="utf-8") for name in ("010_core.sql", "020_identity.sql", "045_workflow.sql", "119_ad_provisioning_wiring.sql")}
    for name, rule in (
        ("010_core.sql", "uq_zones_name"), ("010_core.sql", "uq_zones_code"),
        ("020_identity.sql", "uq_identity_sources_name"), ("020_identity.sql", "uq_identities_source_username"),
        ("020_identity.sql", "directory_flavor"), ("020_identity.sql", "tls_ca_pem"), ("020_identity.sql", "user_filter"),
        ("045_workflow.sql", "fk_access_requests_requester"), ("045_workflow.sql", "original_permission"),
        ("119_ad_provisioning_wiring.sql", "fk_provisioning_jobs_identity_source"),
    ):
        assert rule in core[name], rule
