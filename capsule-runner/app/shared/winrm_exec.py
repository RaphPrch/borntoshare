"""Child process of app.shared.winrm: one PowerShell script over WinRM with the Kerberos cache of its environment.

Reads {"address", "fqdn", "port", "script", "timeout"} on stdin, writes one JSON line on stdout.
"""
from __future__ import annotations

import json
import sys


def _classify(exc: Exception) -> tuple[str, str | None]:
    text = f"{type(exc).__name__}: {exc}".lower()
    if "401" in text or "unauthorized" in text or "access is denied" in text or "accessdenied" in text:
        return "WINRM_ACCESS_DENIED", "The account must be an administrator of the server (FSRM)."
    if "connection refused" in text or "max retries" in text or "timed out" in text or "connecttimeout" in text:
        return "WINRM_UNREACHABLE", "WinRM (TCP 5985) must be open from the worker to the server."
    if "server not found in kerberos database" in text or "spn" in text:
        return "WINRM_SPN_UNKNOWN", "The DNS name of the server is not known by the domain."
    return "WINRM_FAILED", None


def main() -> int:
    request = json.loads(sys.stdin.read() or "{}")
    try:
        from pypsrp.client import Client

        client = Client(
            request["address"], port=int(request.get("port") or 5985), ssl=False, auth="kerberos",
            negotiate_hostname_override=request["fqdn"], negotiate_delegate=False, encryption="always",
            # The receive loop polls every 20 s until the script ends: a long walk of a folder never times out here
            # (the parent process bounds the whole run)
            connection_timeout=min(int(request.get("timeout") or 60), 30),
            operation_timeout=20, read_timeout=30,
        )
        output, streams, had_errors = client.execute_ps(request["script"])
        errors = [str(item) for item in streams.error][:5]
        print(json.dumps({"output": output, "errors": errors, "had_errors": bool(had_errors)}))
    except Exception as exc:  # the parent turns it into a WinRMError
        code, hint = _classify(exc)
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"[:400], "code": code, "hint": hint}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
