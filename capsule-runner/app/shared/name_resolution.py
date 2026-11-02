"""Names of a Windows domain resolved by the DNS servers set for it (Advanced settings > Network and DNS).

The worker container does not always resolve the names of the domains it works with (corp.local, short names
such as FILER01 returned by DFS). For those names it asks the DNS servers of the domain; any other name goes
through the usual resolver. The settings are read from core-service and kept one minute.
"""
from __future__ import annotations

import ipaddress
import random
import socket
import struct
import time
from typing import Any

_CACHE_SECONDS = 60
_dns_map: list[dict[str, Any]] = []
_read_at = 0.0


def _load() -> list[dict[str, Any]]:
    global _dns_map, _read_at
    if _read_at and time.monotonic() - _read_at < _CACHE_SECONDS:
        return _dns_map
    _read_at = time.monotonic()
    try:
        from app.services.core_client import core_get

        data = (core_get("/api/internal/network/dns", timeout=5) or {}).get("data") or []
        _dns_map = [row for row in data if isinstance(row, dict) and row.get("domain") and row.get("servers")]
    except Exception:
        pass  # core-service does not answer: the last known settings stay
    return _dns_map


def is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(str(value).strip())
        return True
    except ValueError:
        return False


def query_a(name: str, server: str, timeout: float = 3.0) -> str | None:
    """First IPv4 address of `name` answered by `server` (one UDP query, no recursion of our own)."""
    labels = [part for part in name.strip(".").split(".") if part]
    if not labels or any(len(part) > 63 for part in labels):
        return None
    question = b"".join(bytes([len(part)]) + part.encode("idna") for part in labels) + b"\x00"
    ident = random.randint(0, 0xFFFF)
    packet = struct.pack(">HHHHHH", ident, 0x0100, 1, 0, 0, 0) + question + struct.pack(">HH", 1, 1)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout)
        sock.sendto(packet, (server, 53))
        data = sock.recv(1024)
    if len(data) < 12 or struct.unpack(">H", data[:2])[0] != ident or data[3] & 0x0F:
        return None
    answers = struct.unpack(">H", data[6:8])[0]
    offset = 12 + len(question) + 4
    for _ in range(answers):
        if data[offset] & 0xC0 == 0xC0:
            offset += 2
        else:
            while data[offset]:
                offset += data[offset] + 1
            offset += 1
        rtype, _rclass, _ttl, length = struct.unpack(">HHIH", data[offset : offset + 10])
        offset += 10
        if rtype == 1 and length == 4:
            return socket.inet_ntoa(data[offset : offset + 4])
        offset += length
    return None


def _system(name: str) -> str | None:
    try:
        return socket.getaddrinfo(name, None, type=socket.SOCK_STREAM)[0][4][0]
    except OSError:
        return None


def domain_resolve(host: str, dns_map: list[dict[str, Any]] | None = None) -> tuple[str, str, str] | None:
    """(address, full name, DNS server) when `host` belongs to a configured domain, else None (usual resolver)."""
    name = str(host or "").strip().rstrip(".")
    if not name or is_ip(name):
        return None
    entries = _load() if dns_map is None else dns_map
    lowered = name.lower()
    for entry in entries:
        domain = str(entry["domain"]).lower().strip(".")
        # A short name (FILER01) is tried in each domain; a full name only in its own
        candidates = [f"{name}.{domain}"] if "." not in name else [name] if lowered == domain or lowered.endswith("." + domain) else []
        for candidate in candidates:
            if entry.get("fallback"):
                # Proposed by a directory, not set by an administrator: the usual resolver goes first
                known = _system(candidate)
                if known:
                    return None if candidate.lower() == lowered else (known, candidate, "system")
            for server in entry["servers"]:
                try:
                    address = query_a(candidate, str(server))
                except OSError:
                    address = None
                if address:
                    return address, candidate, str(server)
    return None


def resolve(host: str) -> str | None:
    """Address of `host`: as is for an IP, by the domain DNS for its names, otherwise by the usual resolver."""
    name = str(host or "").strip()
    if not name:
        return None
    if is_ip(name):
        return name
    found = domain_resolve(name)
    if found:
        return found[0]
    try:
        return socket.getaddrinfo(name, None, type=socket.SOCK_STREAM)[0][4][0]
    except OSError:
        return None


def address_for_tools(host: str) -> str:
    """The host to give Samba and LDAP: its address when only the domain DNS knows it, the name otherwise."""
    found = domain_resolve(host)
    return found[0] if found else host


def resolve_name(params: dict[str, Any]):
    """Test of a name from Advanced settings: what the worker would connect to."""
    name = str(params.get("name") or "").strip()
    if not name:
        return False, "Missing name", {"failure_code": "DNS_NAME_MISSING"}
    found = domain_resolve(name)
    if found:
        return True, "Name resolved", {"name": name, "fqdn": found[1], "address": found[0], "via": found[2]}
    try:
        address = socket.getaddrinfo(name, None, type=socket.SOCK_STREAM)[0][4][0]
        return True, "Name resolved", {"name": name, "fqdn": name, "address": address, "via": "system"}
    except OSError:
        return False, "The name cannot be resolved: check the DNS servers of its domain", {"name": name, "failure_code": "DNS_NAME_UNKNOWN"}
