"""Folder operations on the file server, from Storage roots: NTFS inheritance and deletion of the folder."""
from __future__ import annotations

import logging
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
