"""DNS servers of the Windows domains (Advanced settings > Network and DNS), and the names resolved through them.

Each connected directory proposes its domain controller as the DNS of its domain; an administrator can add or
replace domains. The worker reads the effective list; core-service uses it to recognise a DFS target (FILER01)
as a declared file server (172.20.12.195).
"""
from __future__ import annotations

import ipaddress
import random
import re
import socket
import struct
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

DOMAIN_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
MAX_DOMAINS = 20
MAX_SERVERS = 3


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(str(value).strip())
        return True
    except ValueError:
        return False


def validate_entries(entries: Any) -> str | None:
    """Why the configured list is refused, or None."""
    if not isinstance(entries, list) or len(entries) > MAX_DOMAINS:
        return f"Up to {MAX_DOMAINS} domains"
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            return "Invalid domain entry"
        domain = str(entry.get("domain") or "").strip().lower().strip(".")
        servers = entry.get("servers")
        if not DOMAIN_RE.match(domain):
            return f"Invalid domain name: {domain or '—'}"
        if domain in seen:
            return f"The domain {domain} is listed twice"
        seen.add(domain)
        if not isinstance(servers, list) or not 1 <= len(servers) <= MAX_SERVERS or not all(_is_ip(s) for s in servers):
            return f"{domain}: from 1 to {MAX_SERVERS} DNS servers, given by IP address"
    return None


def configured(db: Session) -> list[dict[str, Any]]:
    from app.api.advanced_settings import _read_payload

    entries = ((_read_payload(db).get("network") or {}).get("dns")) or []
    return [
        {"domain": str(e["domain"]).strip().lower().strip("."), "servers": [str(s).strip() for s in e["servers"]], "origin": "configured"}
        for e in entries
        if isinstance(e, dict) and e.get("domain") and e.get("servers")
    ]


def proposed(db: Session) -> list[dict[str, Any]]:
    """The domain controller of each connected directory, for the domain of that directory."""
    rows = db.execute(
        text(
            "SELECT name, host, domain_name FROM identity_sources "
            "WHERE LOWER(type) = 'ad' AND is_active = 1 AND domain_name IS NOT NULL AND host IS NOT NULL"
        )
    ).mappings().all()
    out: list[dict[str, Any]] = []
    for row in rows:
        host = str(row["host"]).strip()
        if not _is_ip(host):
            try:
                host = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)[0][4][0]
            except OSError:
                continue
        domain = str(row["domain_name"]).strip().lower().strip(".")
        if domain and not any(entry["domain"] == domain for entry in out):
            out.append({"domain": domain, "servers": [host], "origin": "directory", "source": str(row["name"])})
    return out


def effective(db: Session) -> list[dict[str, Any]]:
    """What the worker uses: the domains set by an administrator, then the ones proposed by the directories.
    A proposed domain is only a fallback: its DNS may answer addresses of another network, so the worker
    asks it only for the names its usual resolver does not know."""
    entries = configured(db)
    known = {entry["domain"] for entry in entries}
    return entries + [{**entry, "fallback": True} for entry in proposed(db) if entry["domain"] not in known]


def query_a(name: str, server: str, timeout: float = 2.0) -> str | None:
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
    offset = 12 + len(question) + 4
    for _ in range(struct.unpack(">H", data[6:8])[0]):
        if data[offset] & 0xC0 == 0xC0:
            offset += 2
        else:
            while data[offset]:
                offset += data[offset] + 1
            offset += 1
        rtype, _c, _t, length = struct.unpack(">HHIH", data[offset : offset + 10])
        offset += 10
        if rtype == 1 and length == 4:
            return socket.inet_ntoa(data[offset : offset + 4])
        offset += length
    return None


def addresses(host: str, dns: list[dict[str, Any]]) -> set[str]:
    """Every address `host` may be reached at: itself for an IP, the domain DNS for its names, the usual resolver."""
    name = str(host or "").strip().strip("\\/").rstrip(".")
    if not name:
        return set()
    if _is_ip(name):
        return {name}
    found: set[str] = set()
    lowered = name.lower()
    for entry in dns:
        domain = entry["domain"]
        candidates = [f"{name}.{domain}"] if "." not in name else [name] if lowered == domain or lowered.endswith("." + domain) else []
        for candidate in candidates:
            for server in entry["servers"]:
                try:
                    address = query_a(candidate, server)
                except OSError:
                    address = None
                if address:
                    found.add(address)
                    break
    if not found:
        try:
            found = {info[4][0] for info in socket.getaddrinfo(name, None)}
        except (OSError, UnicodeError):
            pass
    return found
