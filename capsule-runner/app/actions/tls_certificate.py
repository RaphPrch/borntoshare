"""Certificate presented by a directory, read without trusting it: an administrator decides whether to keep it."""
from __future__ import annotations

import hashlib
import socket
import ssl
from typing import Any

from cryptography import x509
from cryptography.x509.oid import ExtensionOID, NameOID


def _common_name(name: x509.Name) -> str:
    values = name.get_attributes_for_oid(NameOID.COMMON_NAME)
    return str(values[0].value) if values else name.rfc4514_string()


def _is_authority(cert: x509.Certificate) -> bool:
    try:
        return bool(cert.extensions.get_extension_for_oid(ExtensionOID.BASIC_CONSTRAINTS).value.ca)
    except x509.ExtensionNotFound:
        return False


def _dns_names(cert: x509.Certificate) -> list[str]:
    try:
        names = cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME).value
    except x509.ExtensionNotFound:
        return []
    return [str(name) for name in names.get_values_for_type(x509.DNSName)]


def fetch_tls_certificate(params: dict[str, Any]):
    host = str(params.get("host") or "").strip()
    port = int(params.get("port") or 636)
    timeout = max(1, min(int(params.get("timeout") or 10), 30))
    details: dict[str, Any] = {"host": host, "port": port}
    if not host:
        return False, "Missing LDAP host", {**details, "failure_code": "TLS_CERT_HOST_MISSING"}

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    try:
        with socket.create_connection((host, port), timeout=timeout) as raw:
            with context.wrap_socket(raw, server_hostname=host) as tls:
                chain = [bytes(item) for item in tls.get_unverified_chain()]
    except ssl.SSLError as exc:
        return False, "This port does not answer in TLS: check the port and that LDAPS is enabled", {
            **details, "failure_code": "TLS_CERT_NOT_TLS", "error": str(exc)[:300],
        }
    except OSError as exc:
        return False, "The directory did not answer: check the host, the port and the firewall", {
            **details, "failure_code": "TLS_CERT_UNREACHABLE", "error": str(exc)[:300],
        }
    if not chain:
        return False, "The directory sent no certificate", {**details, "failure_code": "TLS_CERT_EMPTY"}

    certificates = [x509.load_der_x509_certificate(der) for der in chain]
    server = certificates[0]
    # The authority survives the renewals of the server certificate: kept when the server sends it
    index = next((i for i in range(len(certificates) - 1, 0, -1) if _is_authority(certificates[i])), 0)
    kept = certificates[index]
    return True, "Certificate read", {
        **details,
        "certificate_pem": ssl.DER_cert_to_PEM_cert(chain[index]),
        "is_authority": index > 0 or _is_authority(server),
        "subject": _common_name(kept.subject),
        "issuer": _common_name(kept.issuer),
        "not_after": kept.not_valid_after_utc.isoformat(),
        "sha256": hashlib.sha256(chain[index]).hexdigest(),
        "server_subject": _common_name(server.subject),
        "server_names": _dns_names(server) or [_common_name(server.subject)],
    }
