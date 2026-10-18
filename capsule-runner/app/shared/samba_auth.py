from __future__ import annotations

import os
import subprocess
import tempfile
from typing import Any


def run_samba(cmd: list[str], *, username: str, password: str, **run_kwargs: Any) -> subprocess.CompletedProcess:
    """Run a Samba CLI tool (smbclient, smbcacls, rpcclient) with credentials from a temp auth file.

    Passing `-U user%password` exposes the password in the process list; `-A <file>`
    keeps it in a 0600 file that only lives for the duration of the command.
    """
    fd, auth_path = tempfile.mkstemp(prefix="b2s_smbauth_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(f"username = {username}\npassword = {password}\n")
        return subprocess.run([*cmd, "-A", auth_path], **run_kwargs)
    finally:
        try:
            os.unlink(auth_path)
        except FileNotFoundError:
            pass
