"""H4: the caller is the service whose token is given, never a declared name; the person is the one of a signed
assertion, never a header a caller writes."""
from __future__ import annotations

import asyncio
import time

import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse

from app import main
from app.core import service_identity as si

TOKENS = {"FRONTEND": "f" * 48, "AUTH": "a" * 48, "CAPSULE": "c" * 48, "FIVES": "v" * 48}
KEY = "k" * 48


@pytest.fixture
def per_service(monkeypatch):
    for name, value in TOKENS.items():
        monkeypatch.setenv(f"B2S_TOKEN_{name}", value)
    monkeypatch.setenv("PRINCIPAL_SIGNING_KEY", KEY)
    monkeypatch.setenv("INTERNAL_TOKEN", "shared-token-of-before-0123456789")


def _request(path="/api/zones", method="GET", **headers) -> Request:
    raw = [(k.replace("_", "-").lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({"type": "http", "method": method, "path": path, "headers": raw, "query_string": b""})


def _through(middleware, request):
    seen = {}

    async def call_next(req):
        seen.update({k: v for k, v in req.headers.items()})
        return JSONResponse({"ok": True})

    response = asyncio.run(middleware(request, call_next))
    return response.status_code, seen


def test_the_caller_is_the_owner_of_the_token(per_service) -> None:
    assert si.caller_of(TOKENS["CAPSULE"], None) == "capsule"
    assert si.caller_of("unknown", None) is None
    # The shared token of before no longer opens core-service once the tokens exist
    assert si.caller_of(None, "shared-token-of-before-0123456789") is None


def test_before_the_tokens_the_shared_one_still_works(monkeypatch) -> None:
    for name in TOKENS:
        monkeypatch.delenv(f"B2S_TOKEN_{name}", raising=False)
    monkeypatch.setenv("INTERNAL_TOKEN", "shared-token-of-before-0123456789")
    assert not si.per_service_mode()
    assert si.caller_of(None, "shared-token-of-before-0123456789") == "legacy"


def test_the_worker_only_reaches_its_routes(per_service) -> None:
    ok, _ = _through(main.internal_token_middleware, _request("/api/internal/provisioning/jobs/5", x_service_token=TOKENS["CAPSULE"]))
    refused, _ = _through(main.internal_token_middleware, _request("/api/identity-sources", "POST", x_service_token=TOKENS["CAPSULE"]))
    assert ok == 200 and refused == 403
    # auth-service is not restricted by path; an unknown token is refused
    assert _through(main.internal_token_middleware, _request("/api/identity-sources", x_service_token=TOKENS["AUTH"]))[0] == 200
    assert _through(main.internal_token_middleware, _request("/api/zones", x_service_token="x" * 48))[0] == 403


def test_identity_headers_written_by_a_caller_are_dropped(per_service) -> None:
    _, seen = _through(main.identity_middleware, _request(x_service_token=TOKENS["CAPSULE"], x_identity_id="1", x_roles="platform_admin"))
    assert "x-identity-id" not in seen and "x-roles" not in seen


def test_the_person_of_a_valid_assertion_is_kept(per_service) -> None:
    assertion = si.sign_actor(42, ["platform_admin"], "Alice")
    _, seen = _through(main.identity_middleware, _request(x_b2s_actor=assertion, x_roles="guardian", x_identity_id="7"))
    assert seen["x-identity-id"] == "42" and seen["x-roles"] == "platform_admin" and seen["x-actor-display"] == "Alice"


def test_a_forged_expired_or_misdirected_assertion_names_nobody(per_service) -> None:
    assert si.verify_actor(si.sign_actor(42, ["platform_admin"], None, key=b"other-key")) is None
    assert si.verify_actor(si.sign_actor(42, ["platform_admin"], None, now=time.time() - 120)) is None
    body, signature = si.sign_actor(42, ["guardian"], None).rsplit(".", 1)
    assert si.verify_actor(f"{body}x.{signature}") is None


def test_scopes_come_from_core_not_from_the_caller(per_service) -> None:
    from fastapi import HTTPException

    from app.core.internal_auth import require_internal

    dep = require_internal({"jobs:write"}).dependency
    dep(_request(x_service_token=TOKENS["CAPSULE"]), "", "", "")  # the worker has it
    with pytest.raises(HTTPException) as exc:
        dep(_request(x_service_token=TOKENS["FIVES"], x_service_scope="jobs:write"), "", "fives", "jobs:write")
    assert exc.value.status_code == 403


def test_the_web_interface_is_never_an_internal_service(per_service) -> None:
    from fastapi import HTTPException

    from app.core.internal_auth import require_internal_token

    require_internal_token(_request(x_service_token=TOKENS["AUTH"]))
    with pytest.raises(HTTPException) as exc:
        require_internal_token(_request(x_service_token=TOKENS["FRONTEND"]))
    assert exc.value.status_code == 403


def test_the_diagnostic_says_which_mode(monkeypatch, per_service) -> None:
    from app.services import diagnostics

    assert diagnostics._service_tokens()["result"] == "ok"
    monkeypatch.delenv("PRINCIPAL_SIGNING_KEY")
    assert diagnostics._service_tokens()["result"] == "error"
    for name in TOKENS:
        monkeypatch.delenv(f"B2S_TOKEN_{name}")
    assert diagnostics._service_tokens()["result"] == "warning"


def test_the_web_interface_reaches_the_orchestration_routes(per_service) -> None:
    from fastapi import HTTPException

    from app.core.internal_auth import require_orchestration_access

    require_orchestration_access(_request("/api/governance/probes/run", "POST", x_service_token=TOKENS["FRONTEND"]))
    with pytest.raises(HTTPException):
        require_orchestration_access(_request("/api/governance/probes/run", "POST", x_service_token="x" * 48))
