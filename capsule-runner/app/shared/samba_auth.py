from __future__ import annotations

import os
import subprocess
import tempfile
from typing import Any


def _with_domain_addresses(cmd: list[str]) -> list[str]:
    """//FILER01/share becomes //10.0.0.5/share when only the domain DNS knows FILER01 (Advanced settings)."""
    from app.shared.name_resolution import address_for_tools

    out = list(cmd)
    for index, arg in enumerate(out):
        text = str(arg)
        if text.startswith("//") and len(text) > 2:
            host, _, rest = text[2:].partition("/")
            out[index] = f"//{address_for_tools(host)}" + (f"/{rest}" if rest or _ else "")
        elif index > 0 and out[index - 1] == "-L":
            out[index] = address_for_tools(text.lstrip("/"))
    # rpcclient takes the server as a bare argument
    if out and out[0] == "rpcclient" and len(out) > 1 and not str(out[1]).startswith("-"):
        out[1] = address_for_tools(str(out[1]))
    return out


def run_samba(cmd: list[str], *, username: str, password: str, **run_kwargs: Any) -> subprocess.CompletedProcess:
    """Run a Samba CLI tool (smbclient, smbcacls, rpcclient) with credentials from a temp auth file.

    Passing `-U user%password` exposes the password in the process list; `-A <file>`
    keeps it in a 0600 file that only lives for the duration of the command.
    """
    cmd = _with_domain_addresses(cmd)
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


class stream_samba:
    """A Samba CLI tool whose output is read line by line (a listing of millions of entries never sits in memory).

        with stream_samba(cmd, username=..., password=..., timeout=3600) as lines:
            for line in lines: ...
    The process is killed when the deadline passes (TimeoutError) or when the reader stops early.
    """

    def __init__(self, cmd: list[str], *, username: str, password: str, timeout: int) -> None:
        self.cmd = _with_domain_addresses(cmd)
        self.username = username
        self.password = password
        self.timeout = timeout
        self.proc: subprocess.Popen | None = None
        self.auth_path = ""
        self.timed_out = False

    def __enter__(self):
        import threading

        fd, self.auth_path = tempfile.mkstemp(prefix="b2s_smbauth_")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(f"username = {self.username}\npassword = {self.password}\n")
        self.proc = subprocess.Popen([*self.cmd, "-A", self.auth_path], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self._timer = threading.Timer(self.timeout, self._kill)
        self._timer.start()
        return (raw.decode(errors="ignore").rstrip("\r\n") for raw in self.proc.stdout)

    def _kill(self) -> None:
        self.timed_out = True
        if self.proc and self.proc.poll() is None:
            self.proc.kill()

    def __exit__(self, *exc) -> None:
        self._timer.cancel()
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
        if self.proc:
            self.proc.wait()
        try:
            os.unlink(self.auth_path)
        except FileNotFoundError:
            pass
        if self.timed_out and exc[0] is None:
            raise TimeoutError("listing timed out")

    @property
    def returncode(self) -> int | None:
        return self.proc.returncode if self.proc else None
