"""What a file server says about itself before any account is given: address, SMB version, names and domain.

Nothing here is trusted: the values fill the form, the connection test with the account comes after.
"""
from __future__ import annotations

import re
import socket
import subprocess
from typing import Any

_DIALECT = re.compile(r"negotiated dialect\[([A-Z0-9_]+)\]")
_FIELDS = {
    "netbios_name": re.compile(r"AvNbComputerName\s*:\s*'([^']+)'"),
    "dns_name": re.compile(r"AvDnsComputerName\s*:\s*'([^']+)'"),
    "domain": re.compile(r"AvDnsDomainName\s*:\s*'([^']+)'"),
}
_DIALECT_LABELS = {"SMB3_11": "SMB 3.1.1", "SMB3_02": "SMB 3.0.2", "SMB3_00": "SMB 3.0", "SMB2_10": "SMB 2.1", "SMB2_02": "SMB 2.0.2", "NT1": "SMB 1"}


def describe_negotiation(output: str) -> dict[str, str | None]:
    """SMB version and names announced by the server during the (anonymous) negotiation."""
    dialect = _DIALECT.search(output)
    out: dict[str, str | None] = {"dialect": _DIALECT_LABELS.get(dialect.group(1), dialect.group(1)) if dialect else None}
    for key, pattern in _FIELDS.items():
        match = pattern.search(output)
        out[key] = match.group(1) if match else None
    if out["domain"]:
        out["domain"] = out["domain"].lower()
    return out


def discover_smb_server(params: dict[str, Any]):
    host = str(params.get("host") or "").strip()
    port = int(params.get("port") or 445)
    timeout = max(2, min(int(params.get("timeout") or 8), 20))
    details: dict[str, Any] = {"host": host, "port": port}
    if not host:
        return False, "Missing host", {**details, "failure_code": "SMB_DISCOVERY_HOST_MISSING"}
    from app.shared.name_resolution import resolve

    address = resolve(host)
    if not address:
        return False, "The name of the file server cannot be resolved (DNS)", {**details, "failure_code": "SMB_DISCOVERY_DNS_FAILED"}
    details["address"] = address
    try:
        socket.create_connection((address, port), timeout=timeout).close()
    except OSError:
        return False, f"The file server does not answer on port {port}: check that it is started and that its firewall allows it", {
            **details, "failure_code": "SMB_DISCOVERY_PORT_CLOSED",
        }
    try:
        done = subprocess.run(
            ["smbclient", "-N", "-L", f"//{address}", "-p", str(port), "-m", "SMB3", "-d", "10"],
            capture_output=True, timeout=timeout + 5, check=False,
        )
        output = (done.stdout or b"").decode(errors="ignore") + (done.stderr or b"").decode(errors="ignore")
    except (subprocess.TimeoutExpired, OSError):
        output = ""
    # The anonymous session is refused by most servers: the negotiation before it is what is read
    return True, "File server analysed", {**details, **describe_negotiation(output)}
