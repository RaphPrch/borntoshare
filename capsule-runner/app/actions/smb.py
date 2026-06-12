from __future__ import annotations

import logging
import re
import shutil
import subprocess
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _check(name: str, ok: bool, message: str, **details) -> dict:
    row = {"name": name, "status": "success" if ok else "failed", "message": message}
    if details:
        row["details"] = details
    return row


def _classify_smb_error(stderr: str) -> str:
    value = str(stderr or "").lower()
    if "timeout" in value:
        return "CAPSULE_TIMEOUT"
    if "logon failure" in value or "authentication" in value or "nt_status_logon_failure" in value:
        return "CAPSULE_AUTH_FAILED"
    if "name or service not known" in value or "could not resolve" in value or "dns" in value:
        return "CAPSULE_DNS_FAILED"
    if "connection refused" in value or "nt_status_host_unreachable" in value:
        return "CAPSULE_PORT_UNREACHABLE"
    if "access denied" in value or "nt_status_access_denied" in value:
        return "CAPSULE_PERMISSION_DENIED"
    return "CAPSULE_SMB_FAILED"


def _discover_smb_shares(*, host: str, port: int, username: str, password: str, timeout: int) -> list[str]:
    """Return a best-effort list of SMB shares as UNC paths.

    Notes:
    - We intentionally filter out administrative shares (ending with $) and IPC$.
    - Parsing is strict and machine-readable only (`smbclient -g`).
    """

    # Prefer machine-readable output when available.
    # `-g` is supported by smbclient and is easier to parse.
    cmd = [
        "smbclient",
        "-L",
        host,
        "-U",
        f"{username}%{password}",
        "-m",
        "SMB3",
        "-p",
        str(port),
        "-g",
    ]

    p = subprocess.run(cmd, capture_output=True, timeout=timeout, check=True)
    # smbclient can write useful listing output to stderr depending on version/build.
    out = ((p.stdout or b"") + b"\n" + (p.stderr or b"")).decode(errors="ignore")

    shares: list[str] = []

    # --------------------------------------------------
    # Parse grepable output (best-effort)
    # Typical lines include either:
    # - "Disk|SHARE|Comment" (most common)
    # - "SHARE|Disk|Comment" (less common)
    # --------------------------------------------------
    for line in out.splitlines():
        if "|" not in line:
            continue
        parts = [p.strip() for p in line.split("|") if p.strip()]
        if len(parts) < 2:
            continue

        # Locate the Disk marker.
        disk_idx = None
        for i, token in enumerate(parts):
            if token.lower() == "disk":
                disk_idx = i
                break
        if disk_idx is None:
            continue

        # Derive share name:
        # - if format is Disk|SHARE|Comment => share is after Disk
        # - if format is SHARE|Disk|Comment => share is before Disk
        share = None
        if disk_idx == 0 and len(parts) >= 2:
            share = parts[1]
        elif disk_idx > 0:
            share = parts[disk_idx - 1]

        if not share:
            continue
        if not share or share.upper() == "IPC$" or share.endswith("$"):
            continue

        shares.append(f"\\\\{host}\\{share}")

    # De-dup while keeping order
    seen: set[str] = set()
    uniq: list[str] = []
    for s in shares:
        if s in seen:
            continue
        seen.add(s)
        uniq.append(s)
    return uniq


def _discover_share_permissions(
    *,
    host: str,
    share: str,
    path: str | None = None,
    username: str,
    password: str,
    timeout: int,
) -> list[dict]:
    """Best-effort ACL extraction for a share or a folder via `smbcacls`."""
    share_path = f"//{host}/{share}"
    normalized_path = str(path or "").strip().strip("/\\").replace("/", "\\")
    rel_candidates = [normalized_path, ".", "", "\\"] if normalized_path else ["", "\\", "."]
    out = ""
    tried: set[str] = set()

    for rel_path in rel_candidates:
        if rel_path in tried:
            continue
        tried.add(rel_path)
        cmd = [
            "smbcacls",
            share_path,
            rel_path,
            "-U",
            f"{username}%{password}",
        ]
        try:
            p = subprocess.run(cmd, capture_output=True, timeout=timeout, check=True)
            out = ((p.stdout or b"") + b"\n" + (p.stderr or b"")).decode(errors="ignore")
            if out.strip():
                break
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
            continue

    permissions: list[dict] = []
    seen: set[tuple[str, str, str]] = set()

    for raw in out.splitlines():
        line = raw.strip()
        if not line or not line.startswith("ACL:"):
            continue

        # Typical shape:
        # ACL:DOMAIN\\Group:ALLOWED/0x0/0x00120089
        payload = line[4:]
        if ":" not in payload:
            continue

        principal, rights_raw = payload.split(":", 1)
        principal = principal.strip()
        rights = rights_raw.strip()

        rights_low = rights.lower()
        access_level = "write" if ("0x001301bf" in rights_low or "full" in rights_low) else "read"

        row = {
            "principal": principal,
            "access_level": access_level,
            "raw": rights,
            "source": "smbcacls",
        }
        key = (row["principal"], row["access_level"], row["raw"])
        if key in seen:
            continue
        seen.add(key)
        permissions.append(row)

    return permissions


def _parse_smbclient_du_bytes(output: str) -> int | None:
    text = str(output or "").strip()
    if not text:
        return None

    patterns = (
        r"Total number of bytes:\s*([0-9][0-9,]*)",
        r"total\s+number\s+of\s+bytes\s*[:=]?\s*([0-9][0-9,]*)",
        r"([0-9][0-9,]*)\s+bytes\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        try:
            return int(match.group(1).replace(",", ""))
        except ValueError:
            continue

    return None


def _discover_share_content_size(
    *,
    host: str,
    share: str,
    path: str | None = None,
    username: str,
    password: str,
    port: int,
    timeout: int,
) -> tuple[int | None, dict]:
    normalized_path = str(path or "").strip().strip("/\\").replace("\\", "/")
    du_target = normalized_path or ""
    cmd = [
        "smbclient",
        f"//{host}/{share}",
        "-U",
        f"{username}%{password}",
        "-m",
        "SMB3",
        "-p",
        str(port),
        "-c",
        f'du "{du_target}"',
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout, check=True)
        output = ((proc.stdout or b"") + b"\n" + (proc.stderr or b"")).decode(errors="ignore")
        size_bytes = _parse_smbclient_du_bytes(output)
        if size_bytes is None:
            return None, {
                "supported": False,
                "failure_code": "CAPSULE_SMB_DU_PARSE_FAILED",
                "stderr": ((proc.stderr or b"").decode(errors="ignore") or "")[:2000],
                "stdout": ((proc.stdout or b"").decode(errors="ignore") or "")[:2000],
            }
        return size_bytes, {
            "supported": True,
            "command": "du",
        }
    except subprocess.CalledProcessError as exc:
        stderr = ((exc.stderr or b"").decode(errors="ignore") or "")[:2000]
        return None, {
            "supported": False,
            "failure_code": _classify_smb_error(stderr),
            "stderr": stderr,
            "stdout": ((exc.stdout or b"").decode(errors="ignore") or "")[:2000],
        }
    except subprocess.TimeoutExpired:
        return None, {
            "supported": False,
            "failure_code": "CAPSULE_TIMEOUT",
            "timeout": int(timeout),
        }
    except OSError as exc:
        return None, {
            "supported": False,
            "failure_code": "CAPSULE_SMB_DU_UNAVAILABLE",
            "error": str(exc)[:2000],
        }


def test_smb_ntlm(params: dict):
    host = params["host"]
    username = params["username"]
    password = params["password"]
    port = int(params.get("port", 445))
    timeout = int(params.get("timeout", 10))
    discover = bool(params.get("discover", False))

    cmd = [
        "smbclient",
        f"//{host}/IPC$",
        "-U", f"{username}%{password}",
        "-m", "SMB3",
        "-p", str(port),
        "-c", "exit",
    ]

    try:
        subprocess.run(cmd, capture_output=True, timeout=timeout, check=True)
        details = {
            "host": host,
            "port": port,
            "dialect": "SMB3",
            "reachable": True,
            "authenticated": True,
            "acl_capability": shutil.which("smbcacls") is not None,
            "discovery_complete": False,
            "checks": [_check("smb_auth", True, "SMB IPC authentication successful")],
        }
        if details["acl_capability"]:
            details["checks"].append(_check("acl_capability", True, "SMB ACL inspection available via smbcacls"))
        else:
            details["checks"].append(
                _check(
                    "acl_capability",
                    False,
                    "SMB ACL inspection unavailable: smbcacls is not installed",
                    failure_code="CAPSULE_SMBCACLS_UNAVAILABLE",
                )
            )

        endpoint_id = params.get("storage_endpoint_id")
        try:
            endpoint_id = int(endpoint_id) if endpoint_id is not None else None
        except (TypeError, ValueError):
            endpoint_id = None
        if endpoint_id:
            details["storage_endpoint_id"] = endpoint_id

        if discover:
            try:
                roots = _discover_smb_shares(
                    host=host,
                    port=port,
                    username=username,
                    password=password,
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired:
                details["checks"].append(_check("share_discovery", False, "SMB share discovery timeout"))
                details["failure_code"] = "CAPSULE_TIMEOUT"
                return True, "Connection OK but share discovery timed out", details
            except subprocess.CalledProcessError as e:
                stderr = (e.stderr or b"").decode(errors="ignore")
                details["checks"].append(
                    _check(
                        "share_discovery",
                        False,
                        "SMB share discovery failed",
                        stderr=stderr[:4000],
                    )
                )
                details["failure_code"] = _classify_smb_error(stderr)
                return True, "Connection OK but share discovery failed", details
            except OSError as e:
                details["checks"].append(
                    _check(
                        "share_discovery",
                        False,
                        "SMB share discovery unavailable",
                        error=str(e)[:2000],
                    )
                )
                details["failure_code"] = "CAPSULE_SMB_DISCOVERY_UNAVAILABLE"
                return True, "Connection OK but share discovery unavailable", details

            details["roots"] = roots
            details["permissions_by_root"] = {}
            details["discovered_at"] = datetime.now(timezone.utc).isoformat()
            details["discovery_complete"] = True
            details["checks"].append(
                _check("share_discovery", True, "SMB share discovery successful", roots_count=len(roots))
            )

            if details["acl_capability"]:
                for unc in roots:
                    # UNC shape: \\host\share
                    parts = [p for p in str(unc).split("\\") if p]
                    share = parts[1] if len(parts) >= 2 else ""
                    if not share:
                        continue
                    perms = _discover_share_permissions(
                        host=host,
                        share=share,
                        username=username,
                        password=password,
                        timeout=timeout,
                    )
                    details["permissions_by_root"][unc] = perms

            # Optional UX hint: keep message informative when discovery is empty.
            if not roots:
                return True, "Connection OK but no shares discovered", details

        return True, "SMB NTLM authentication successful", details
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or b"").decode(errors="ignore")
        return False, "SMB authentication failed", {
            "host": host,
            "port": port,
            "stderr": stderr[:4000],
            "reachable": False,
            "authenticated": False,
            "failure_code": _classify_smb_error(stderr),
            "checks": [_check("smb_auth", False, "SMB IPC authentication failed", stderr=stderr[:4000])],
        }
    except subprocess.TimeoutExpired:
        return False, "SMB connection timeout", {
            "host": host,
            "port": port,
            "reachable": False,
            "authenticated": False,
            "failure_code": "CAPSULE_TIMEOUT",
            "checks": [_check("smb_auth", False, "SMB connection timeout")],
        }


def test_smb_root_access(params: dict):
    host = params["host"]
    share = params["share"]
    rel_path = str(params.get("path") or "").strip().strip("/\\")
    username = params["username"]
    password = params["password"]
    port = int(params.get("port", 445))
    timeout = int(params.get("timeout", 10))
    discover_permissions = bool(params.get("discover_permissions", True))
    discover_content_size = bool(params.get("discover_content_size", True))

    smb_path = f"//{host}/{share}"
    display_rel_path = rel_path.replace("/", "\\")
    target_label = f"\\\\{host}\\{share}" + (f"\\{display_rel_path}" if display_rel_path else "")
    ls_target = rel_path.replace("\\", "/") if rel_path else ""

    cmd = [
        "smbclient",
        smb_path,
        "-U",
        f"{username}%{password}",
        "-m",
        "SMB3",
        "-p",
        str(port),
        "-c",
        f'ls "{ls_target}"',
    ]
    safe_cmd = [
        "smbclient",
        smb_path,
        "-U",
        f"{username}%***",
        "-m",
        "SMB3",
        "-p",
        str(port),
        "-c",
        f'ls "{ls_target}"',
    ]

    details = {
        "host": host,
        "port": port,
        "share": share,
        "path": rel_path,
        "root_path": target_label,
        "dialect": "SMB3",
        "storage_endpoint_id": params.get("storage_endpoint_id"),
        "storage_root_id": params.get("storage_root_id"),
        "checks": [],
    }

    logger.info(
        "SMB root probe requested",
        extra={
            "operation": "test_smb_root_access",
            "host": host,
            "share": share,
            "path": rel_path,
            "storage_root_id": params.get("storage_root_id"),
            "storage_endpoint_id": params.get("storage_endpoint_id"),
            "command": safe_cmd,
        },
    )

    try:
        subprocess.run(cmd, capture_output=True, timeout=timeout, check=True)
        details["reachable"] = True
        details["authenticated"] = True
        details["root_accessible"] = True
        details["checks"].append(_check("root_read", True, "SMB storage root is readable", root_path=target_label))
        if discover_permissions:
            if shutil.which("smbcacls") is None:
                details["permissions"] = []
                details["permissions_count"] = 0
                details["permissions_error"] = "smbcacls_unavailable"
                details["checks"].append(
                    _check(
                        "root_acl",
                        False,
                        "SMB ACL inspection unavailable: smbcacls is not installed",
                        root_path=target_label,
                        error_code="CAPSULE_SMBCACLS_UNAVAILABLE",
                    )
                )
            else:
                permissions = _discover_share_permissions(
                    host=host,
                    share=share,
                    path=rel_path,
                    username=username,
                    password=password,
                    timeout=timeout,
                )
                details["permissions"] = permissions
                details["permissions_count"] = len(permissions)
                details["permissions_discovered_at"] = datetime.now(timezone.utc).isoformat()
                details["checks"].append(
                    _check(
                        "root_acl",
                        True,
                        "SMB storage root ACL inspected",
                        root_path=target_label,
                        permissions_count=len(permissions),
                    )
                )
        else:
            details["checks"].append(_check("root_acl", True, "SMB storage root ACL inspection skipped"))

        if discover_content_size:
            content_size_bytes, size_meta = _discover_share_content_size(
                host=host,
                share=share,
                path=rel_path,
                username=username,
                password=password,
                port=port,
                timeout=timeout,
            )
            if content_size_bytes is not None:
                details["content_size_bytes"] = content_size_bytes
                details["content_updated_at"] = datetime.now(timezone.utc).isoformat()
                details["checks"].append(
                    _check(
                        "root_content_size",
                        True,
                        "SMB storage root content size estimated",
                        content_size_bytes=int(content_size_bytes),
                        method=str(size_meta.get("command") or "du"),
                    )
                )
            else:
                details["checks"].append(
                    _check(
                        "root_content_size",
                        False,
                        "SMB storage root content size unavailable",
                        **size_meta,
                    )
                )
        else:
            details["checks"].append(
                _check("root_content_size", True, "SMB storage root content size skipped")
            )
        return True, "SMB storage root reachable", details
    except subprocess.CalledProcessError as e:
        stdout = (e.stdout or b"").decode(errors="ignore")
        stderr = (e.stderr or b"").decode(errors="ignore")
        diagnostic_output = stderr or stdout
        failure_code = _classify_smb_error(diagnostic_output)
        failure_reason = diagnostic_output[:4000].strip()
        failure_message = (
            f"SMB storage root read failed: {failure_reason}"
            if failure_reason
            else "SMB storage root read failed"
        )
        details["reachable"] = False
        details["authenticated"] = False
        details["root_accessible"] = False
        details["stdout"] = stdout[:4000]
        details["stderr"] = stderr[:4000]
        details["failure_code"] = failure_code
        details["command"] = safe_cmd
        logger.warning(
            "SMB root probe failed",
            extra={
                "operation": "test_smb_root_access",
                "host": host,
                "share": share,
                "path": rel_path,
                "root_path": target_label,
                "storage_root_id": params.get("storage_root_id"),
                "storage_endpoint_id": params.get("storage_endpoint_id"),
                "failure_code": failure_code,
                "stdout": stdout[:2000],
                "stderr": stderr[:2000],
                "command": safe_cmd,
            },
        )
        details["checks"].append(
            _check(
                "root_read",
                False,
                failure_message,
                stdout=stdout[:4000],
                stderr=stderr[:4000],
            )
        )
        return False, failure_message, details
    except subprocess.TimeoutExpired:
        details["reachable"] = False
        details["authenticated"] = False
        details["root_accessible"] = False
        details["failure_code"] = "CAPSULE_TIMEOUT"
        details["command"] = safe_cmd
        logger.warning(
            "SMB root probe timed out",
            extra={
                "operation": "test_smb_root_access",
                "host": host,
                "share": share,
                "path": rel_path,
                "root_path": target_label,
                "storage_root_id": params.get("storage_root_id"),
                "storage_endpoint_id": params.get("storage_endpoint_id"),
                "failure_code": "CAPSULE_TIMEOUT",
                "command": safe_cmd,
            },
        )
        details["checks"].append(_check("root_read", False, "SMB storage root read timeout"))
        return False, "SMB storage root read timeout", details
