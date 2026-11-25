"""H4: auth-service names itself to core-service by its own token, and signs the person it acts for."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from app.core.config import get_settings
from app.core.internal_token import actor_assertion, build_internal_headers


def test_its_own_token_goes_with_every_call(monkeypatch) -> None:
    monkeypatch.setenv("B2S_SERVICE_TOKEN", "a" * 48)
    headers = build_internal_headers("rid-1")
    assert headers["X-Service-Token"] == "a" * 48 and headers["X-Request-ID"] == "rid-1"
    monkeypatch.delenv("B2S_SERVICE_TOKEN")
    assert "X-Service-Token" not in build_internal_headers()


def test_the_person_is_signed_in_the_format_of_core() -> None:
    body, signature = actor_assertion(42, ["Platform_Admin"], "Alice").rsplit(".", 1)
    key = get_settings().PRINCIPAL_SIGNING_KEY.encode()
    expected = base64.urlsafe_b64encode(hmac.new(key, body.encode(), hashlib.sha256).digest()).rstrip(b"=").decode()
    assert hmac.compare_digest(signature, expected)
    payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    assert payload["id"] == 42 and payload["roles"] == ["platform_admin"] and payload["aud"] == "core"
    assert 0 < payload["exp"] - time.time() <= 60
