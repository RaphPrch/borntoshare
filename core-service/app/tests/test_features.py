"""License keys: signed offline, tampered or foreign keys refused, and what they open."""
from __future__ import annotations

import base64
import json
import struct
from datetime import date

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.core import license_keys
from app.services import features


def _issue(private: Ed25519PrivateKey, **payload) -> str:
    """Same encoding as scripts/license/issue_license.py."""
    body = json.dumps({"lic": "abc123", "cust": "CORP", "feat": ["fives"], "iat": "2026-11-09", "exp": "2027-12-31", "lim": {}, **payload},
                      separators=(",", ":"), sort_keys=True).encode()
    head = struct.pack(">BH", 1, len(body))
    text = base64.b32encode(head + body + private.sign(head + body)).decode().rstrip("=")
    return "B2S-" + "-".join(text[i:i + 5] for i in range(0, len(text), 5))


@pytest.fixture()
def issuer(monkeypatch):
    private = Ed25519PrivateKey.generate()
    pem = private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    monkeypatch.setattr(license_keys, "PUBLIC_KEYS", [pem])
    return private


def test_a_signed_key_opens_its_features(issuer) -> None:
    lic = features.decode(_issue(issuer, lim={"max_tb": 40}))
    assert lic.customer == "CORP" and lic.features == ("fives",) and lic.expires_on == date(2027, 12, 31) and lic.limits == {"max_tb": 40}
    assert lic.valid_on(date(2027, 12, 31)) and not lic.valid_on(date(2028, 1, 1))


def test_spaces_case_and_line_breaks_do_not_matter(issuer) -> None:
    key = _issue(issuer)
    messy = key.lower().replace("-", " ")
    messy = "  " + messy[:30] + "\n" + messy[30:] + " "
    assert features.decode(messy).license_id == "abc123"


def test_a_tampered_or_foreign_key_is_refused(issuer) -> None:
    key = _issue(issuer)
    tampered = key[:-7] + ("A" if key[-7] != "A" else "B") + key[-6:]
    with pytest.raises(features.LicenseError) as refused:
        features.decode(tampered)
    assert refused.value.code in {"LICENSE_SIGNATURE_INVALID", "LICENSE_MALFORMED"}
    with pytest.raises(features.LicenseError) as foreign:
        features.decode(_issue(Ed25519PrivateKey.generate()))
    assert foreign.value.code == "LICENSE_SIGNATURE_INVALID"
    with pytest.raises(features.LicenseError):
        features.decode("hello world, this is not a key at all")


def test_the_embedded_public_key_is_an_ed25519_key() -> None:
    for pem in license_keys.PUBLIC_KEYS:
        assert serialization.load_pem_public_key(pem.encode()).public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw).__len__() == 32
