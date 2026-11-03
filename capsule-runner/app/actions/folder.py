"""Folder operations on the file server, from Storage roots: NTFS inheritance, deletion, sub-folder creation."""
from __future__ import annotations

import logging
import re
import subprocess
from typing import Any, Dict

from app.shared.samba_auth import run_samba
from app.shared.windows_names import folder_name_error, share_name_error

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
        message = next((line for line in _output(done).splitlines() if "NT_STATUS_" in line), "le dossier est toujours présent")
        return False, message.strip()[:300], {**details, "failure_code": "FOLDER_DELETE_FAILED"}
    logger.info("Folder deleted", extra={"operation": "folder_delete", "target_share": share, "target_path": path})
    return True, "Folder deleted", details


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
        message = next((line for line in created_output.splitlines() if "NT_STATUS_" in line), "le dossier n'a pas été créé")
        return False, message.strip()[:300], {**details, "failure_code": "FOLDER_CREATE_FAILED"}
    details["created"] = True
    logger.info("Folder created", extra={"operation": "folder_create", "target_share": share, "target_path": path})
    return True, "Folder created", details


LOCAL_PATH = re.compile(r"^([A-Za-z]):((?:\\[^\\/:*?\"<>|]+)+)$")


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
        return False, r"Un chemin local du serveur est attendu, par exemple D:\Shares\Finance", {**details, "failure_code": "SHARE_PATH_INVALID"}
    parts = [part for part in matched.group(2).split("\\") if part]
    commands = "; ".join(f'mkdir "{chr(92).join(parts[:depth + 1])}"' for depth in range(len(parts)))
    try:
        existing = run_samba(["rpcclient", host, "-c", f'netsharegetinfo "{share}" 1'],
                             username=user, password=password, capture_output=True, timeout=timeout)
        if f"netname: {share}".lower() in _output(existing).lower():
            return False, "Un partage porte déjà ce nom.", {**details, "failure_code": "SHARE_EXISTS"}
        folder = run_samba(["smbclient", f"//{host}/{matched.group(1).upper()}$", "-c", commands],
                           username=user, password=password, capture_output=True, timeout=timeout)
        folder_output = _output(folder)
        if "NT_STATUS_ACCESS_DENIED" in folder_output or "NT_STATUS_BAD_NETWORK_NAME" in folder_output:
            return False, ("Le compte du serveur de fichiers n'accède pas au partage administratif : "
                           "il doit être administrateur local du serveur."), {**details, "failure_code": "SHARE_ADMIN_REQUIRED"}
        # -1: no limit of connections (0 would refuse every connection to the share)
        added = run_samba(["rpcclient", host, "-c", f'netshareadd "{local_path}" "{share}" -1 "BornToShare"'],
                          username=user, password=password, capture_output=True, timeout=timeout)
        check = run_samba(["rpcclient", host, "-c", f'netsharegetinfo "{share}" 2'],
                          username=user, password=password, capture_output=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, f"Impossible de créer le partage : {exc}", {**details, "failure_code": "SHARE_CREATE_FAILED"}
    added_output = _output(added)
    check_output = _output(check)
    if "WERR_ACCESS_DENIED" in added_output:
        return False, "Le compte du serveur de fichiers doit être administrateur local du serveur.", {**details, "failure_code": "SHARE_ADMIN_REQUIRED"}
    if local_path.lower() not in check_output.lower():
        message = next((line for line in added_output.splitlines() if "WERR_" in line or "NT_STATUS_" in line), "le partage n'a pas été créé")
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
        return False, f"Partage créé, mais ses permissions n'ont pas pu être posées : {exc}", {**details, "failure_code": "SHARE_ACL_FAILED"}
    if "S-1-5-32-544" not in listing or "S-1-5-32-545" in listing or "S-1-1-0" in listing:
        return False, "Partage créé, mais son dossier reste ouvert aux utilisateurs du serveur.", {**details, "failure_code": "SHARE_ACL_FAILED"}
    details["created"] = True
    logger.info("Share created", extra={"operation": "share_create", "target_share": share})
    return True, "Share created", details


# Shares of the system, never removed from BornToShare
SYSTEM_SHARES = {"IPC$", "ADMIN$", "PRINT$", "NETLOGON", "SYSVOL"}


def delete_share(params: Dict[str, Any]):
    """Remove a share from a Windows file server over RPC. Its folder and files stay on the server."""
    host = str(params.get("host") or "").strip()
    share = str(params.get("share") or "")
    user = _auth_user(str(params.get("username") or "").strip(), str(params.get("domain") or "").strip())
    password = str(params.get("password") or "")
    timeout = int(params.get("timeout_sec") or 30)
    details: dict[str, Any] = {"operation": "share_delete", "target": {"host": host, "share": share}}

    if share_name_error(share) or share.upper() in SYSTEM_SHARES or share.endswith("$"):
        return False, "Ce partage ne peut pas être supprimé depuis BornToShare.", {**details, "failure_code": "SHARE_NAME_INVALID"}
    try:
        existing = _output(run_samba(["rpcclient", host, "-c", f'netsharegetinfo "{share}" 2'],
                                     username=user, password=password, capture_output=True, timeout=timeout))
        if "WERR_ACCESS_DENIED" in existing or "NT_STATUS_ACCESS_DENIED" in existing:
            return False, "Le compte du serveur de fichiers doit être administrateur local du serveur.", {**details, "failure_code": "SHARE_ADMIN_REQUIRED"}
        if f"netname: {share}".lower() not in existing.lower():
            return False, "Ce partage n'existe pas sur le serveur.", {**details, "failure_code": "SHARE_NOT_FOUND"}
        path = next((line.split(":", 1)[1].strip() for line in existing.splitlines() if line.strip().lower().startswith("path:")), "")
        removed = _output(run_samba(["rpcclient", host, "-c", f'netsharedel "{share}"'],
                                    username=user, password=password, capture_output=True, timeout=timeout))
        check = _output(run_samba(["rpcclient", host, "-c", f'netsharegetinfo "{share}" 1'],
                                  username=user, password=password, capture_output=True, timeout=timeout))
    except (subprocess.TimeoutExpired, OSError) as exc:
        return False, f"Impossible de supprimer le partage : {exc}", {**details, "failure_code": "SHARE_DELETE_FAILED"}
    if "WERR_ACCESS_DENIED" in removed:
        return False, "Le compte du serveur de fichiers doit être administrateur local du serveur.", {**details, "failure_code": "SHARE_ADMIN_REQUIRED"}
    if f"netname: {share}".lower() in check.lower():
        message = next((line for line in removed.splitlines() if "WERR_" in line or "NT_STATUS_" in line), "le partage est toujours là")
        code = "SHARE_IN_USE" if "WERR_" in message and "IN_USE" in message.upper() else "SHARE_DELETE_FAILED"
        return False, message.strip()[:300], {**details, "failure_code": code}
    details.update({"deleted": True, "path": path, "folder_removed": False})
    matched = LOCAL_PATH.match(path)
    if params.get("remove_empty_folder") and matched:
        # rmdir refuses a folder that is not empty: nothing in it can be lost
        try:
            removed_dir = _output(run_samba(["smbclient", f"//{host}/{matched.group(1).upper()}$", "-c", f'rmdir "{matched.group(2).lstrip(chr(92))}"'],
                                            username=user, password=password, capture_output=True, timeout=timeout))
            details["folder_removed"] = "NT_STATUS_" not in removed_dir
            if not details["folder_removed"]:
                details["folder_kept_because"] = "not_empty" if "NOT_EMPTY" in removed_dir.upper() else "refused"
        except (subprocess.TimeoutExpired, OSError):
            details["folder_kept_because"] = "refused"
    logger.info("Share deleted", extra={"operation": "share_delete", "target_share": share})
    return True, "Share deleted", details
