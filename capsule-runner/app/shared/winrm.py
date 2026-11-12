"""PowerShell on a Windows server over WinRM (PSRP on HTTP 5985, Kerberos message encryption).

Kerberos only: no NTLM fallback, no delegation (the lab's CIS choice). The account gets its ticket with kinit in a
cache of its own (a temporary folder per call) and the session runs in a child process that only sees this cache:
two jobs at once never share a ticket, and the password goes through stdin, never a command line.

Kerberos needs the DNS name of the server (its HTTP/<name> SPN). A server declared by its IP is matched with the
name it has in Servers (FILER01 or FILER01.corp.local), checked against the domain DNS.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from app.shared import name_resolution

WINRM_PORT = 5985
_APP_ROOT = str(Path(__file__).resolve().parents[2])


class WinRMError(RuntimeError):
    def __init__(self, code: str, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint


def _domains() -> list[str]:
    try:
        return [str(entry["domain"]).strip(".").lower() for entry in name_resolution._load()]
    except Exception:
        return []


def realm_of(username: str, domain: str = "") -> str:
    """CORP.LOCAL for user@corp.local, for CORP\\user (NetBIOS name matched with the configured DNS domains)
    or for the domain of the directory."""
    name = str(username or "").strip()
    if "@" in name:
        return name.rsplit("@", 1)[1].upper()
    domain = str(domain or "").strip().strip(".")
    if "." in domain:
        return domain.upper()
    netbios = (name.split("\\", 1)[0] if "\\" in name else domain).lower()
    for candidate in _domains():
        if netbios and candidate.split(".", 1)[0] == netbios:
            return candidate.upper()
    raise WinRMError("WINRM_REALM_UNKNOWN", "The Kerberos domain of the account is unknown",
                     hint="Write the account as user@domain.local, or declare the domain DNS in Advanced settings.")


def principal_of(username: str, realm: str) -> str:
    bare = str(username or "").strip().split("\\")[-1].split("@")[0]
    return f"{bare}@{realm}"


def kdcs_of(realm: str, hint: str | None = None) -> list[str]:
    """Domain controllers: the directory host first, then the A records of the domain from its DNS."""
    out: list[str] = []
    # Every controller of the directory host (« AD01, AD02 »), in order, then the domain's A records
    for name in name_resolution.hosts_of(hint):
        address = name_resolution.resolve(name) or name
        if address not in out:
            out.append(address)
    domain = realm.lower()
    try:
        entries = name_resolution._load()
    except Exception:
        entries = []
    for entry in entries:
        if str(entry.get("domain", "")).strip(".").lower() != domain:
            continue
        for server in entry.get("servers") or []:
            try:
                address = name_resolution.query_a(domain, str(server))
            except OSError:
                address = None
            out.append(address or str(server))
    unique = list(dict.fromkeys(item for item in out if item))
    if not unique:
        raise WinRMError("WINRM_KDC_UNKNOWN", f"No domain controller found for {realm}",
                         hint="Declare the DNS of the domain in Advanced settings.")
    return unique


def server_fqdn(host: str, server_name: str | None, realm: str) -> str:
    """DNS name of the server, for its Kerberos SPN."""
    host = str(host or "").strip()
    suffix = realm.lower()
    if host and not name_resolution.is_ip(host):
        return host if "." in host else f"{host}.{suffix}"
    name = str(server_name or "").strip().rstrip(".")
    if name and not name_resolution.is_ip(name) and " " not in name:
        candidate = name if "." in name else f"{name}.{suffix}"
        found = None
        for _attempt in range(3):  # one UDP question each: a busy DNS can drop one
            found = name_resolution.domain_resolve(candidate)
            if found:
                break
        if found and found[0] != host:
            raise WinRMError("WINRM_SERVER_NAME_MISMATCH", f"{candidate} answers {found[0]}, not {host}",
                             hint="The name of the server in Servers must be its DNS name.")
        # Resolved to this server, or no answer: Kerberos checks the name anyway (its ticket is only for the right SPN)
        return found[1] if found else candidate
    raise WinRMError("WINRM_SERVER_NAME_UNKNOWN", f"The DNS name of {host} is unknown: Kerberos needs it",
                     hint="Name the server with its DNS name (FILER01.corp.local) in Servers.")


def _krb5_conf(realm: str, kdcs: list[str]) -> str:
    kdc_lines = "".join(f"  kdc = {kdc}\n" for kdc in kdcs)
    return (
        "[libdefaults]\n"
        f" default_realm = {realm}\n"
        " dns_lookup_kdc = false\n dns_lookup_realm = false\n rdns = false\n"
        " udp_preference_limit = 0\n forwardable = false\n"
        f"[realms]\n {realm} = {{\n{kdc_lines} }}\n"
    )


def run_powershell(*, host: str, server_name: str | None, username: str, password: str, domain: str = "",
                   kdc_hint: str | None = None, script: str, timeout: int = 60) -> dict[str, Any]:
    """Run `script` on the server; {"output": str, "errors": [...]} or WinRMError."""
    realm = realm_of(username, domain)
    fqdn = server_fqdn(host, server_name, realm)
    kdcs = kdcs_of(realm, kdc_hint)
    address = host if name_resolution.is_ip(host) else (name_resolution.resolve(host) or host)
    with TemporaryDirectory(prefix="b2s_krb_") as folder:
        conf = Path(folder) / "krb5.conf"
        conf.write_text(_krb5_conf(realm, kdcs), encoding="utf-8")
        env = {**os.environ, "KRB5_CONFIG": str(conf), "KRB5CCNAME": f"FILE:{folder}/ccache"}
        try:
            done = subprocess.run(["kinit", principal_of(username, realm)], input=password.encode(), capture_output=True,
                                  timeout=min(timeout, 20), env=env)
        except subprocess.TimeoutExpired as exc:
            raise WinRMError("WINRM_KERBEROS_TIMEOUT", f"No answer from the domain controller ({', '.join(kdcs)})") from exc
        if done.returncode != 0:
            detail = (done.stderr or b"").decode(errors="ignore").strip().splitlines()
            raise WinRMError("WINRM_KERBEROS_FAILED", f"Kerberos refused the account: {detail[-1] if detail else 'kinit failed'}"[:400],
                             hint="Check the account and password of the server in Servers.")
        request = {"address": address, "fqdn": fqdn, "port": WINRM_PORT, "script": script, "timeout": timeout}
        try:
            child = subprocess.run([sys.executable, "-m", "app.shared.winrm_exec"], input=json.dumps(request).encode(),
                                   capture_output=True, timeout=timeout + 15, env=env, cwd=_APP_ROOT)
        except subprocess.TimeoutExpired as exc:
            raise WinRMError("WINRM_TIMEOUT", f"{fqdn} did not answer in {timeout} s") from exc
    lines = [line for line in (child.stdout or b"").decode(errors="ignore").splitlines() if line.strip()]
    try:
        result = json.loads(lines[-1]) if lines else {}
    except ValueError:
        result = {}
    if not result:
        stderr = (child.stderr or b"").decode(errors="ignore").strip()
        raise WinRMError("WINRM_FAILED", (stderr.splitlines() or ["WinRM session failed"])[-1][:400])
    if result.get("error"):
        raise WinRMError(str(result.get("code") or "WINRM_FAILED"), str(result["error"])[:400], hint=result.get("hint"))
    return {"output": str(result.get("output") or ""), "errors": list(result.get("errors") or [])}
