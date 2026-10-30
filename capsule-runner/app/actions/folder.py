"""Folder operations on the file server, from Storage roots: NTFS inheritance, deletion, sub-folder creation."""
from __future__ import annotations

import logging
import re
import subprocess
from typing import Any, Dict

from app.shared.samba_auth import run_samba

logger = logging.getLogger(__name__)

# smbcacls --inherit: copy = break and keep the inherited entries as explicit ones (Windows « convert »),
# allow = inherit again from the parent folder
INHERIT_MODES = {"break": "copy", "restore": "allow"}


def _auth_user(username: str, domain: str) -> str:
    if "\\" in username or "@" in username or not domain:
        return username
    return f"{domain}\\{username}"


def _rel_path(raw: Any) -> str:
    """Folder inside the share, Windows separators; never the share itself nor a parent reference."""
    parts = [p for p in str(raw or "").replace("/", "\\").split("\\") if p]
    if not parts or any(p in {".", ".."} for p in parts):
        return ""
    return "\\".join(parts)


def _output(done: subprocess.CompletedProcess) -> str:
    return ((done.stdout or b"") + b"\n" + (done.stderr or b"")).decode(errors="ignore")


def _control(host: str, share: str, path: str, user: str, password: str, timeout: int) -> str:
    done = run_samba(["smbcacls", f"//{host}/{share}", path], username=user, password=password, capture_output=True, timeout=timeout)
    for line in _output(done).splitlines():
        if line.strip().startswith("CONTROL:"):
            return line.strip()[8:]
    return ""


def set_folder_inheritance(params: Dict[str, Any]):
    """Break (keeping the inherited entries as explicit ones) or restore the NTFS inheritance of a folder."""
    host = str(params.get("host") or "").strip()
    share = str(params.get("share") or "").strip()
    path = _rel_path(params.get("path"))
    mode = str(params.get("inheritance") or "").strip().lower()
    user = _auth_user(str(params.get("username") or "").strip(), str(params.get("domain") or "").strip())
    password = str(params.get("password") or "")
    timeout = int(params.get("timeout_sec") or 20)
    details: dict[str, Any] = {"operation": "folder_inheritance", "target": {"host": host, "share": share, "path": path}, "mode": mode}

    if mode not in INHERIT_MODES:
        return False, "Invalid mode", {**details, "failure_code": "FOLDER_INHERITANCE_MODE_INVALID"}
    if not path:
        return False, "The inheritance of a share root cannot change", {**details, "failure_code": "FOLDER_PATH_REQUIRED"}
    try:
        done = run_samba(["smbcacls", f"//{host}/{share}", path, f"--inherit={INHERIT_MODES[mode]}"],
                         username=user, password=password, capture_output=True, timeout=timeout)
        control = _control(host, share, path, user, password, timeout)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, f"smbcacls failed: {exc}", {**details, "failure_code": "FOLDER_INHERITANCE_FAILED"}
    output = _output(done)
    # smbcacls may exit 0 without changing anything: the CONTROL flags read back decide
    protected = "PD" in control.split("|")
    details.update({"control": control, "inheritance_broken": protected})
    if done.returncode != 0 or "NT_STATUS_" in output or protected != (mode == "break"):
        return False, (output.strip().splitlines() or ["inheritance unchanged"])[-1][:300], {**details, "failure_code": "FOLDER_INHERITANCE_FAILED"}
    logger.info("Folder inheritance changed", extra={"operation": "folder_inheritance", "mode": mode, "target_share": share, "target_path": path})
    return True, "Inheritance broken" if protected else "Inheritance restored", details


def delete_folder(params: Dict[str, Any]):
    """Delete the folder of a storage root and everything in it (smbclient deltree), then check it is gone."""
    host = str(params.get("host") or "").strip()
    share = str(params.get("share") or "").strip()
    path = _rel_path(params.get("path"))
    user = _auth_user(str(params.get("username") or "").strip(), str(params.get("domain") or "").strip())
    password = str(params.get("password") or "")
    timeout = int(params.get("timeout_sec") or 60)
    details: dict[str, Any] = {"operation": "folder_delete", "target": {"host": host, "share": share, "path": path}}

    if not path:
        return False, "A share root is never deleted", {**details, "failure_code": "FOLDER_PATH_REQUIRED"}
    quoted = path.replace('"', "")
    try:
        done = run_samba(["smbclient", f"//{host}/{share}", "-c", f'deltree "{quoted}"'],
                         username=user, password=password, capture_output=True, timeout=timeout)
        check = run_samba(["smbclient", f"//{host}/{share}", "-c", f'ls "{quoted}"'],
                          username=user, password=password, capture_output=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, f"smbclient failed: {exc}", {**details, "failure_code": "FOLDER_DELETE_FAILED"}
    remaining = _output(check)
    gone = "NT_STATUS_NO_SUCH_FILE" in remaining or "NT_STATUS_OBJECT_NAME_NOT_FOUND" in remaining or "NT_STATUS_OBJECT_PATH_NOT_FOUND" in remaining
    details["deleted"] = gone
    if not gone:
        message = next((line for line in _output(done).splitlines() if "NT_STATUS_" in line), "the folder is still there")
        return False, message.strip()[:300], {**details, "failure_code": "FOLDER_DELETE_FAILED"}
    logger.info("Folder deleted", extra={"operation": "folder_delete", "target_share": share, "target_path": path})
    return True, "Folder deleted", details


# Characters Windows refuses in a file or folder name
_FORBIDDEN_NAME_CHARS = set('\\/:*?"<>|')


def folder_name_error(name: str) -> str | None:
    """Why a sub-folder name is refused, or None when it is valid."""
    if not name or name in {".", ".."}:
        return "The folder name is empty"
    if len(name) > 255:
        return "The folder name is longer than 255 characters"
    if any(c in _FORBIDDEN_NAME_CHARS or ord(c) < 32 for c in name):
        return 'The folder name contains a character refused by Windows (\\ / : * ? " < > |)'
    if name != name.strip() or name.endswith("."):
        return "The folder name cannot start or end with a space, nor end with a dot"
    return None


def create_subfolder(params: Dict[str, Any]):
    """Create a sub-folder in the folder of a storage root (smbclient mkdir), then check it exists."""
    host = str(params.get("host") or "").strip()
    share = str(params.get("share") or "").strip()
    parent = _rel_path(params.get("path"))
    name = str(params.get("folder_name") or "")
    user = _auth_user(str(params.get("username") or "").strip(), str(params.get("domain") or "").strip())
    password = str(params.get("password") or "")
    timeout = int(params.get("timeout_sec") or 30)
    path = f"{parent}\\{name}" if parent else name
    details: dict[str, Any] = {"operation": "folder_create", "target": {"host": host, "share": share, "path": path}}

    error = folder_name_error(name)
    if error:
        return False, error, {**details, "failure_code": "FOLDER_NAME_INVALID"}
    try:
        done = run_samba(["smbclient", f"//{host}/{share}", "-c", f'mkdir "{path}"'],
                         username=user, password=password, capture_output=True, timeout=timeout)
        check = run_samba(["smbclient", f"//{host}/{share}", "-c", f'cd "{path}"'],
                          username=user, password=password, capture_output=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, f"smbclient failed: {exc}", {**details, "failure_code": "FOLDER_CREATE_FAILED"}
    created_output = _output(done)
    if "NT_STATUS_OBJECT_NAME_COLLISION" in created_output:
        return False, "A folder with this name already exists", {**details, "failure_code": "FOLDER_EXISTS"}
    if "NT_STATUS_" in _output(check):
        message = next((line for line in created_output.splitlines() if "NT_STATUS_" in line), "the folder was not created")
        return False, message.strip()[:300], {**details, "failure_code": "FOLDER_CREATE_FAILED"}
    details["created"] = True
    logger.info("Folder created", extra={"operation": "folder_create", "target_share": share, "target_path": path})
    return True, "Folder created", details


SHARE_NAME_FORBIDDEN = re.compile(r'[\\/:*?"<>|\[\];=,+$]')
LOCAL_PATH = re.compile(r"^([A-Za-z]):((?:\\[^\\/:*?\"<>|]+)+)$")


def share_name_error(name: str) -> str | None:
    if not name.strip() or name != name.strip() or len(name) > 80:
        return "The share name is required, 80 characters at most, without surrounding spaces"
    if SHARE_NAME_FORBIDDEN.search(name):
        return 'These characters are refused in a share name: \\ / : * ? " < > | [ ] ; = , + $'
    return None


def create_share(params: Dict[str, Any]):
    """Create a share on a Windows file server: its folder through the administrative share, the share over RPC, then read it back."""
    host = str(params.get("host") or "").strip()
    share = str(params.get("share") or "")
    local_path = str(params.get("path") or "").strip()
    user = _auth_user(str(params.get("username") or "").strip(), str(params.get("domain") or "").strip())
    password = str(params.get("password") or "")
    timeout = int(params.get("timeout_sec") or 30)
    details: dict[str, Any] = {"operation": "share_create", "target": {"host": host, "share": share, "path": local_path}}

    error = share_name_error(share)
    if error:
        return False, error, {**details, "failure_code": "SHARE_NAME_INVALID"}
    matched = LOCAL_PATH.match(local_path)
    if not matched:
        return False, r"A local path of the server is expected, like D:\Shares\Finance", {**details, "failure_code": "SHARE_PATH_INVALID"}
    parts = [part for part in matched.group(2).split("\\") if part]
    commands = "; ".join(f'mkdir "{chr(92).join(parts[:depth + 1])}"' for depth in range(len(parts)))
    try:
        existing = run_samba(["rpcclient", host, "-c", f'netsharegetinfo "{share}" 1'],
                             username=user, password=password, capture_output=True, timeout=timeout)
        if f"netname: {share}".lower() in _output(existing).lower():
            return False, "A share with this name already exists", {**details, "failure_code": "SHARE_EXISTS"}
        folder = run_samba(["smbclient", f"//{host}/{matched.group(1).upper()}$", "-c", commands],
                           username=user, password=password, capture_output=True, timeout=timeout)
        folder_output = _output(folder)
        if "NT_STATUS_ACCESS_DENIED" in folder_output or "NT_STATUS_BAD_NETWORK_NAME" in folder_output:
            return False, ("The account of the file server cannot reach the administrative share: "
                           "it must be a local administrator of the server"), {**details, "failure_code": "SHARE_ADMIN_REQUIRED"}
        # -1: no limit of connections (0 would refuse every connection to the share)
        added = run_samba(["rpcclient", host, "-c", f'netshareadd "{local_path}" "{share}" -1 "BornToShare"'],
                          username=user, password=password, capture_output=True, timeout=timeout)
        check = run_samba(["rpcclient", host, "-c", f'netsharegetinfo "{share}" 2'],
                          username=user, password=password, capture_output=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, f"Unable to create the share: {exc}", {**details, "failure_code": "SHARE_CREATE_FAILED"}
    added_output = _output(added)
    check_output = _output(check)
    if "WERR_ACCESS_DENIED" in added_output:
        return False, "The account of the file server must be a local administrator of the server", {**details, "failure_code": "SHARE_ADMIN_REQUIRED"}
    if local_path.lower() not in check_output.lower():
        message = next((line for line in added_output.splitlines() if "WERR_" in line or "NT_STATUS_" in line), "the share was not created")
        return False, message.strip()[:300], {**details, "failure_code": "SHARE_CREATE_FAILED"}
    # Without this, the folder inherits from the drive: every user of the domain could read it (BUILTIN\\Users)
    entries = [r"S-1-5-18", r"S-1-5-32-544", user]
    try:
        for entry in entries:
            run_samba(["smbcacls", f"//{host}/{share}", "\\", "--add", f"ACL:{entry}:ALLOWED/OI|CI/FULL"],
                      username=user, password=password, capture_output=True, timeout=timeout)
        run_samba(["smbcacls", f"//{host}/{share}", "\\", "--inherit=remove"],
                  username=user, password=password, capture_output=True, timeout=timeout)
        listing = _output(run_samba(["smbcacls", f"//{host}/{share}", "\\", "--numeric"],
                                    username=user, password=password, capture_output=True, timeout=timeout))
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, f"Share created, but its permissions could not be set: {exc}", {**details, "failure_code": "SHARE_ACL_FAILED"}
    if "S-1-5-32-544" not in listing or "S-1-5-32-545" in listing or "S-1-1-0" in listing:
        return False, "Share created, but its folder is still open to the users of the server", {**details, "failure_code": "SHARE_ACL_FAILED"}
    details["created"] = True
    logger.info("Share created", extra={"operation": "share_create", "target_share": share})
    return True, "Share created", details
