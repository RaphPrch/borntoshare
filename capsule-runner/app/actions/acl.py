from __future__ import annotations

import logging
import re
import shutil
import subprocess
import time
from typing import Any, Dict

logger = logging.getLogger(__name__)

NTFS_MASK_READ_EXECUTE = "0x001200a9"
NTFS_MASK_WRITE_MODIFY = "0x001301bf"
NTFS_MASK_AUDIT_READ_SECURITY = "0x00020000"

ACE_FLAGS_THIS_FOLDER_SUBFOLDERS_FILES = "OI|CI"

ACL_SCOPE_THIS_FOLDER_SUBFOLDERS_FILES = "this_folder_subfolders_files"

NTFS_MASKS_BY_PERMISSION = {
    "read": NTFS_MASK_READ_EXECUTE,
    "write": NTFS_MASK_WRITE_MODIFY,
    "audit": NTFS_MASK_AUDIT_READ_SECURITY,
}

ACE_FLAGS_BY_SCOPE = {
    ACL_SCOPE_THIS_FOLDER_SUBFOLDERS_FILES: ACE_FLAGS_THIS_FOLDER_SUBFOLDERS_FILES,
}

_SID_RE = re.compile(r"(S-\d-(?:\d+-){1,14}\d+)")


def _ace_principal_candidates(ad_group_name: str, domain: str) -> list[str]:
    raw_group = str(ad_group_name or "").strip()
    raw_domain = str(domain or "").strip()
    if not raw_group:
        return []

    candidates: list[str] = []
    if ("\\" in raw_group) or ("/" in raw_group) or ("@" in raw_group):
        candidates.append(raw_group)
    else:
        if raw_domain:
            candidates.append(f"{raw_domain}\\{raw_group}")
        candidates.append(raw_group)

    seen: set[str] = set()
    out: list[str] = []
    for candidate in candidates:
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(candidate)
    return out


def _domain_from_username(username: str) -> str:
    raw = str(username or "").strip()
    if "\\" not in raw:
        return ""
    domain, _sep, _user = raw.partition("\\")
    return domain.strip()


def _lookup_sid_via_rpcclient(
    *,
    host: str,
    auth_user: str,
    password: str,
    principal: str,
    timeout: int,
) -> str | None:
    if not shutil.which("rpcclient"):
        return None

    lookup = str(principal or "").strip()
    if not lookup:
        return None

    cmd = [
        "rpcclient",
        host,
        "-U",
        f"{auth_user}%{password}",
        "-c",
        f"lookupnames {lookup}",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=max(1, min(timeout, 10)), check=True)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None

    output = ((proc.stdout or b"") + b"\n" + (proc.stderr or b"")).decode(errors="ignore")
    match = _SID_RE.search(output)
    return match.group(1) if match else None


def _resolved_ace_principals(
    *,
    ad_group_name: str,
    domain: str,
    host: str,
    auth_user: str,
    password: str,
    timeout: int,
) -> list[str]:
    base_candidates = _ace_principal_candidates(ad_group_name, domain)
    if not base_candidates:
        return []

    sid_candidates: list[str] = []
    for candidate in base_candidates:
        sid = _lookup_sid_via_rpcclient(
            host=host,
            auth_user=auth_user,
            password=password,
            principal=candidate,
            timeout=timeout,
        )
        if sid:
            sid_candidates.append(sid)

    seen: set[str] = set()
    out: list[str] = []
    for candidate in [*base_candidates, *sid_candidates]:
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(candidate)
    return out


def _principal_type(value: str) -> str:
    return "sid" if _SID_RE.fullmatch(str(value or "").strip()) else "name"


def _attempts_show_principal_resolution_failure(attempts: list[dict[str, Any]]) -> bool:
    for attempt in attempts:
        text = f"{attempt.get('stdout') or ''}\n{attempt.get('stderr') or ''}".lower()
        if "failed to convert" in text or "none_mapped" in text:
            return True
    return False


def _failure_message_from_attempts(attempts: list[dict[str, Any]], ad_group_name: str) -> str:
    if _attempts_show_principal_resolution_failure(attempts):
        return f"ACL principal cannot be resolved by SMB server: {ad_group_name}"
    for attempt in reversed(attempts):
        stderr = str(attempt.get("stderr") or "").strip()
        stdout = str(attempt.get("stdout") or "").strip()
        if stderr:
            return f"ACL apply failed: {stderr[:300]}"
        if stdout:
            return f"ACL apply failed: {stdout[:300]}"
    return "ACL apply failed"


def apply_acl_via_group(params: Dict[str, Any]):
    """Apply SMB/NTFS-like ACL via AD group using smbcacls.

    Inputs expected:
      - host: SMB server
      - share: SMB share name
      - path: optional folder path inside share
      - ad_group_name: AD group to grant
      - permission: read | write | audit
      - username/password (+ optional domain)
      - options.dry_run (optional, default False)
      - options.timeout_sec (optional, default 20)
    """

    host = str(params.get("host") or "").strip()
    share = str(params.get("share") or "").strip()
    path = str(params.get("path") or "").strip().strip("/")
    ad_group_name = str(params.get("ad_group_name") or "").strip()
    permission = str(params.get("permission") or "").strip().lower()
    username = str(params.get("username") or "").strip()
    password = str(params.get("password") or "").strip()
    domain = str(params.get("domain") or "").strip()
    if not domain:
        domain = _domain_from_username(username)

    options = params.get("options") if isinstance(params.get("options"), dict) else {}
    dry_run = bool(options.get("dry_run", False))
    timeout = int(options.get("timeout_sec") or params.get("timeout_sec") or 20)

    if not host:
        return False, "Missing required field: host", {"field": "host"}
    if not share:
        return False, "Missing required field: share", {"field": "share"}
    if not ad_group_name:
        return False, "Missing required field: ad_group_name", {"field": "ad_group_name"}
    if permission not in {"read", "write", "audit"}:
        return False, "Invalid permission", {
            "field": "permission",
            "allowed": ["read", "write", "audit"],
            "got": permission,
        }
    if not username:
        return False, "Missing required field: username", {"field": "username"}
    if not password:
        return False, "Missing required field: password", {"field": "password"}

    # smbcacls expects a Samba ACL mask (or hex mask), not Windows labels like
    # "Read" / "Modify". Using explicit masks avoids parser differences.
    ntfs_mask = NTFS_MASKS_BY_PERMISSION[permission]
    acl_scope = ACL_SCOPE_THIS_FOLDER_SUBFOLDERS_FILES
    ace_flags = ACE_FLAGS_BY_SCOPE[acl_scope]

    unc = f"\\\\{host}\\{share}"
    if path:
        unc = f"{unc}\\{path}"

    details = {
        "target": {
            "host": host,
            "share": share,
            "path": path,
            "unc": unc,
        },
        "subject": {
            "ad_group_name": ad_group_name,
        },
        "auth": {
            "username": username,
            "domain": domain or None,
        },
        "permission": permission,
        "ntfs_mask": ntfs_mask,
        "ace_flags": ace_flags,
        "acl_scope": acl_scope,
        "ace_principals": [],
        "dry_run": dry_run,
        "applied": False,
        "operation": "acl_apply_via_group",
        "tool": "smbcacls",
    }

    if dry_run:
        return True, "ACL plan generated (dry-run)", details

    share_path = f"//{host}/{share}"
    auth_user = username if ("\\" in username or "@" in username) else f"{domain}\\{username}" if domain else username

    ace_principals = _resolved_ace_principals(
        ad_group_name=ad_group_name,
        domain=domain,
        host=host,
        auth_user=auth_user,
        password=password,
        timeout=timeout,
    )
    details["ace_principals"] = ace_principals

    # `smbcacls` requires a filename argument. At share root, "." may fail with
    # NT_STATUS_OBJECT_NAME_INVALID depending on Samba/server behavior.
    rel_candidates = [path] if path else ["", "\\"]
    attempts: list[dict[str, Any]] = []

    logger.info(
        "ACL apply requested",
        extra={
            "operation": "acl_apply_via_group",
            "ad_group_name": ad_group_name,
            "target_unc": unc,
            "permission": permission,
            "ntfs_mask": ntfs_mask,
            "ace_flags": ace_flags,
            "acl_scope": acl_scope,
            "ace_principals": ace_principals,
            "dry_run": dry_run,
        },
    )

    deadline = time.monotonic() + max(1, timeout)
    resolution_retry = 0
    while True:
        for ace_principal in ace_principals:
            ace = f"ACL:{ace_principal}:ALLOWED/{ace_flags}/{ntfs_mask}"
            for rel_path in rel_candidates:
                cmd = [
                    "smbcacls",
                    share_path,
                    rel_path,
                    "-U",
                    f"{auth_user}%{password}",
                    "--add",
                    ace,
                ]
                safe_cmd = [
                    "smbcacls",
                    share_path,
                    rel_path,
                    "-U",
                    f"{auth_user}%***",
                    "--add",
                    ace,
                ]

                logger.info(
                    "Executing smbcacls ACL apply",
                    extra={
                        "operation": "acl_apply_via_group",
                        "ad_group_name": ad_group_name,
                        "ace_principal": ace_principal,
                        "selected_principal_type": _principal_type(ace_principal),
                        "target_unc": unc,
                        "resolved_rel_path": rel_path,
                        "permission": permission,
                        "ntfs_mask": ntfs_mask,
                        "ace_flags": ace_flags,
                        "command": safe_cmd,
                        "resolution_retry": resolution_retry,
                    },
                )

                try:
                    p = subprocess.run(cmd, capture_output=True, timeout=timeout, check=True)
                    details["applied"] = True
                    details["resolved_rel_path"] = rel_path
                    details["resolved_principal"] = ace_principal
                    details["selected_principal_type"] = _principal_type(ace_principal)
                    details["stdout"] = ((p.stdout or b"").decode(errors="ignore") or "")[:4000]
                    details["attempts"] = attempts
                    details["command"] = safe_cmd
                    if details["selected_principal_type"] == "sid":
                        logger.warning(
                            "ACL applied using SID fallback",
                            extra={
                                "operation": "acl_apply_via_group",
                                "ad_group_name": ad_group_name,
                                "resolved_principal": ace_principal,
                                "selected_principal_type": "sid",
                                "target_unc": unc,
                                "ace_flags": ace_flags,
                                "ntfs_mask": ntfs_mask,
                                "note": "Windows may keep displaying the ACE as a SID if the file server cannot resolve the group name.",
                            },
                        )
                    return True, "ACL applied", details
                except subprocess.CalledProcessError as e:
                    attempts.append(
                        {
                            "principal": ace_principal,
                            "rel_path": rel_path,
                            "command": safe_cmd,
                            "stdout": ((e.stdout or b"").decode(errors="ignore") or "")[:1000],
                            "stderr": ((e.stderr or b"").decode(errors="ignore") or "")[:1000],
                        }
                    )
                    continue
                except subprocess.TimeoutExpired:
                    details["timeout_sec"] = timeout
                    details["attempts"] = attempts
                    details["command"] = safe_cmd
                    return False, "ACL apply timeout", details

        if not _attempts_show_principal_resolution_failure(attempts) or time.monotonic() + 2 > deadline:
            break
        resolution_retry += 1
        time.sleep(2)
        ace_principals = _resolved_ace_principals(
            ad_group_name=ad_group_name,
            domain=domain,
            host=host,
            auth_user=auth_user,
            password=password,
            timeout=timeout,
        )
        details["ace_principals"] = ace_principals

    details["attempts"] = attempts
    if attempts:
        details["command"] = attempts[-1].get("command")
        details["stdout"] = attempts[-1].get("stdout") or ""
        details["stderr"] = attempts[-1].get("stderr") or ""
    return False, _failure_message_from_attempts(attempts, ad_group_name), details
