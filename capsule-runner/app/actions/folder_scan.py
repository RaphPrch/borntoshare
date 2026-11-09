"""Measure of a governed folder, apart from its test: a job of its own, on the scan queue (its own worker threads).

On a Windows file server the walk runs ON the server (PowerShell over WinRM, app.shared.server_scan): size, age,
clutter, probable duplicates and fingerprints of the biggest files, without a listing crossing the network.
Elsewhere (no WinRM, a DFS namespace, a Samba server) the folder is listed through SMB, read as it streams
(never all in memory), without duplicates.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict

from app.actions.folder import _rel_path
from app.actions.smb import _JUNK, _classify_smb_error, parse_recursive_ls
from app.shared.samba_auth import stream_samba
from app.shared.server_scan import ServerScanError, measure
from app.shared.winrm import WinRMError

logger = logging.getLogger(__name__)


def _smb_measure(host: str, share: str, path: str, username: str, password: str, port: int, timeout: int) -> dict[str, Any]:
    pattern = f"{path}\\*" if path else "*"
    cmd = ["smbclient", f"//{host}/{share}", "-m", "SMB3", "-p", str(port), "-c", f'recurse ON; ls "{pattern}"']
    tail: list[str] = []

    def keep(lines):
        for line in lines:
            if "NT_STATUS_" in line and len(tail) < 5:
                tail.append(line)
            yield line

    with stream_samba(cmd, username=username, password=password, timeout=timeout) as lines:
        stats = parse_recursive_ls(keep(lines), base=path)
    if not stats["files"] and not stats["folders"] and tail:
        raise RuntimeError(tail[-1])
    return {**stats, "method": "smb"}


def scan_folder(params: Dict[str, Any]):
    host = str(params.get("host") or "").strip()
    share = str(params.get("share") or "").strip()
    path = _rel_path(params.get("path"))
    username = str(params.get("username") or "").strip()
    password = str(params.get("password") or "")
    timeout = int(params.get("timeout_sec") or 3600)
    started = time.monotonic()
    details: dict[str, Any] = {"operation": "folder_scan", "target": {"host": host, "share": share, "path": path},
                               "storage_root_id": params.get("storage_root_id")}
    fallback_reason = None
    stats: dict[str, Any] | None = None
    if params.get("server_name") or not _is_ip(host):
        try:
            stats = measure(share=share, path=path, junk_pattern=_JUNK.pattern, timeout=timeout,
                            connection={"host": host, "server_name": params.get("server_name"), "username": username, "password": password,
                                        "domain": str(params.get("domain") or ""), "kdc_hint": params.get("kdc_host")})
        except (WinRMError, ServerScanError) as exc:
            fallback_reason = f"{getattr(exc, 'code', 'WINRM_FAILED')}: {getattr(exc, 'message', str(exc))}"[:300]
            logger.info("Server-side scan unavailable, SMB listing", extra={"operation": "folder_scan", "reason": fallback_reason})
    if stats is None:
        try:
            stats = _smb_measure(host, share, path, username, password, int(params.get("port") or 445), timeout)
        except TimeoutError:
            return False, f"The listing of the folder took more than {timeout} s", {**details, "failure_code": "SCAN_TIMEOUT"}
        except RuntimeError as exc:
            return False, f"The folder could not be listed: {exc}"[:400], {**details, "failure_code": _classify_smb_error(str(exc))}
    fingerprints = stats.pop("fingerprints", None) or []
    elapsed = int((time.monotonic() - started) * 1000)
    stats["elapsed_ms"] = elapsed
    details.update({
        "content_stats": stats,
        "content_size_bytes": int(stats.get("bytes") or 0),
        "fingerprints": fingerprints,
        "scan_method": stats.get("method"),
        "fallback_reason": fallback_reason,
    })
    return True, f"{stats.get('files', 0)} file(s), {stats.get('bytes', 0)} bytes in {elapsed} ms ({stats.get('method')})", details


def _is_ip(value: str) -> bool:
    from app.shared.name_resolution import is_ip

    return is_ip(value)

