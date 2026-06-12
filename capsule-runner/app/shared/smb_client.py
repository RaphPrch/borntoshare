from __future__ import annotations

import subprocess
from typing import Any


def probe_path(
    *,
    host: str,
    username: str,
    password: str,
    port: int = 445,
    timeout: int = 10,
) -> tuple[bool, str, dict[str, Any]]:
    cmd = [
        "smbclient",
        f"//{str(host or '').strip()}/IPC$",
        "-U",
        f"{str(username or '').strip()}%{str(password or '')}",
        "-m",
        "SMB3",
        "-p",
        str(int(port)),
        "-c",
        "exit",
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=int(timeout), check=True)
        return True, "SMB probe successful", {"host": host, "port": int(port), "dialect": "SMB3"}
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or b"").decode(errors="ignore")
        return False, "SMB probe failed", {"host": host, "port": int(port), "stderr": stderr[:4000]}
    except subprocess.TimeoutExpired:
        return False, "SMB probe timeout", {"host": host, "port": int(port), "timeout": int(timeout)}


def apply_acl(
    *,
    host: str,
    share: str,
    rel_path: str,
    ad_group_name: str,
    permission_mask: str,
    username: str,
    password: str,
    domain: str = "",
    timeout: int = 20,
) -> tuple[bool, str, dict[str, Any]]:
    share_path = f"//{str(host or '').strip()}/{str(share or '').strip()}"
    auth_user = f"{domain}\\{username}" if str(domain or "").strip() else str(username or "").strip()
    ace = f"ACL:{str(ad_group_name or '').strip()}:ALLOWED/0/{str(permission_mask or '').strip()}"

    attempts: list[dict[str, str]] = []
    for candidate in [str(rel_path or "").strip().strip("/"), "", "\\", "."]:
        cmd = [
            "smbcacls",
            share_path,
            candidate,
            "-U",
            f"{auth_user}%{str(password or '')}",
            "--add",
            ace,
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=int(timeout), check=True)
            return True, "ACL applied", {
                "host": host,
                "share": share,
                "path": candidate,
                "stdout": ((proc.stdout or b"").decode(errors="ignore") or "")[:4000],
                "attempts": attempts,
            }
        except subprocess.CalledProcessError as exc:
            attempts.append(
                {
                    "path": candidate,
                    "stdout": ((exc.stdout or b"").decode(errors="ignore") or "")[:1000],
                    "stderr": ((exc.stderr or b"").decode(errors="ignore") or "")[:1000],
                }
            )
            continue
        except subprocess.TimeoutExpired:
            return False, "ACL apply timeout", {"host": host, "share": share, "attempts": attempts}

    return False, "ACL apply failed", {"host": host, "share": share, "attempts": attempts}

