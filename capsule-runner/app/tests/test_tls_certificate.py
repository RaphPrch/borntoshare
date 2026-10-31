from __future__ import annotations

import datetime as dt
import ssl

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from app.actions import tls_certificate as action


def _certificate(name: str, *, ca: bool = False, issuer: tuple[str, object] | None = None) -> tuple[bytes, object]:
    key = ec.generate_private_key(ec.SECP256R1())
    now = dt.datetime.now(dt.timezone.utc)
    builder = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)]))
        .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issuer[0] if issuer else name)]))
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + dt.timedelta(days=10))
        .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
    )
    if not ca:
        builder = builder.add_extension(x509.SubjectAlternativeName([x509.DNSName(name)]), critical=False)
    cert = builder.sign(issuer[1] if issuer else key, hashes.SHA256())
    return cert.public_bytes(serialization.Encoding.DER), key


def _serve(monkeypatch, chain: list[bytes]) -> None:
    class _Tls:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def get_unverified_chain(self):
            return chain

    class _Raw(_Tls):
        pass

    monkeypatch.setattr(action.socket, "create_connection", lambda *a, **k: _Raw())
    monkeypatch.setattr(ssl.SSLContext, "wrap_socket", lambda self, raw, server_hostname=None: _Tls())


def test_a_server_certificate_alone_is_kept_and_described(monkeypatch) -> None:
    ca_der, ca_key = _certificate("Lab CA", ca=True)
    leaf, _ = _certificate("dc01.example.test", issuer=("Lab CA", ca_key))
    _serve(monkeypatch, [leaf])

    ok, _message, details = action.fetch_tls_certificate({"host": "10.0.0.1"})

    assert ok is True
    assert details["is_authority"] is False
    assert details["subject"] == "dc01.example.test" and details["issuer"] == "Lab CA"
    assert details["server_names"] == ["dc01.example.test"]
    assert ssl.PEM_cert_to_DER_cert(details["certificate_pem"]) == leaf
    assert len(details["sha256"]) == 64


def test_the_authority_is_preferred_when_the_server_sends_it(monkeypatch) -> None:
    ca_der, ca_key = _certificate("Lab CA", ca=True)
    leaf, _ = _certificate("dc01.example.test", issuer=("Lab CA", ca_key))
    _serve(monkeypatch, [leaf, ca_der])

    ok, _message, details = action.fetch_tls_certificate({"host": "10.0.0.1"})

    assert ok is True and details["is_authority"] is True
    assert details["subject"] == "Lab CA"
    assert details["server_names"] == ["dc01.example.test"]
    assert ssl.PEM_cert_to_DER_cert(details["certificate_pem"]) == ca_der


def test_an_unreachable_directory_is_explained(monkeypatch) -> None:
    def refused(*_a, **_k):
        raise OSError("refused")

    monkeypatch.setattr(action.socket, "create_connection", refused)
    ok, _message, details = action.fetch_tls_certificate({"host": "10.0.0.1"})
    assert ok is False and details["failure_code"] == "TLS_CERT_UNREACHABLE"
