"""Names Windows accepts for a folder, a share and a DFS folder: the same rules, and the same messages, in the core
(refused before any job) and in the worker (refused before touching the server). This file has a twin in
core-service/app/services/windows_names.py: a test of the core checks they stay the same."""
from __future__ import annotations

import re

# Characters Windows refuses in a file or folder name
FORBIDDEN_NAME_CHARS = set('\\/:*?"<>|')
RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL", *{f"COM{n}" for n in range(1, 10)}, *{f"LPT{n}" for n in range(1, 10)}}
SHARE_NAME_FORBIDDEN = re.compile(r'[\\/:*?"<>|\[\];=,+$]')

RESERVED_MESSAGE = "This name is reserved by Windows"


def folder_name_error(name: str) -> str | None:
    """Why a folder name is refused, or None when it is valid."""
    if not name or name in {".", ".."}:
        return "The folder name is empty"
    if name.split(".")[0].upper() in RESERVED_NAMES:
        return RESERVED_MESSAGE
    if len(name) > 255:
        return "The folder name is longer than 255 characters"
    if any(c in FORBIDDEN_NAME_CHARS or ord(c) < 32 for c in name):
        return 'The folder name contains a character refused by Windows (\\ / : * ? " < > |)'
    if name != name.strip() or name.endswith("."):
        return "The folder name cannot start or end with a space, nor end with a dot"
    return None


def share_name_error(name: str) -> str | None:
    """Why a share name is refused, or None when it is valid."""
    if not name.strip() or name != name.strip() or len(name) > 80:
        return "The share name is required, 80 characters at most, without surrounding spaces"
    if SHARE_NAME_FORBIDDEN.search(name):
        return 'These characters are refused in a share name: \\ / : * ? " < > | [ ] ; = , + $'
    return None


def dfs_folder_error(folder: str) -> str | None:
    """Why a DFS folder (Corporate\\Finance: levels separated by \\) is refused, or None when it is valid."""
    if not folder.strip("\\") or len(folder) > 255:
        return "The name of the DFS folder is required, 255 characters at most"
    for part in folder.strip("\\").split("\\"):
        error = folder_name_error(part)
        if error:
            return error
    return None
