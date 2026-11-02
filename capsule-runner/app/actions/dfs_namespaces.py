"""DFS namespaces hosted by a server: their folders (links) and the shares they lead to (targets).

One method for domain namespaces (\\\\corp.local\\name) and standalone ones (\\\\DFS01\\name): the root share is walked
over SMB, every DFS folder is a reparse point, and the server tells its targets through a DFS referral (the request
Windows Explorer makes). Read only, with the account of the DFS server.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Iterable

from app.shared.name_resolution import resolve
from app.shared.samba_auth import run_samba

_SYSTEM_SHARES = {"ADMIN$", "IPC$", "PRINT$", "SYSVOL", "NETLOGON"}
_REPARSE_POINT = 0x400
_MAX_DEPTH = 8


def _clean_target(path: str) -> str:
    """\\\\FILER01\\Share as the server wrote it (single or double leading backslash)."""
    return "\\\\" + str(path or "").lstrip("\\")


def walk_links(
    root: str,
    list_dir: Callable[[str], Iterable[tuple[str, bool, bool]]],
    *,
    max_links: int,
    max_depth: int = _MAX_DEPTH,
) -> list[str]:
    """Relative paths of the DFS folders under `root`: reparse points, looked for in the ordinary folders."""
    found: list[str] = []
    pending: list[tuple[str, int]] = [("", 0)]
    while pending and len(found) < max_links:
        rel, depth = pending.pop(0)
        for name, is_dir, is_reparse in list_dir(root + ("\\" + rel if rel else "")):
            if not is_dir or name in {".", ".."}:
                continue
            child = f"{rel}\\{name}" if rel else name
            if is_reparse:
                found.append(child)
            elif depth + 1 < max_depth:
                pending.append((child, depth + 1))
    return found[:max_links]


def _root_server(path: str, *, username: str, password: str, port: int) -> tuple[str, str] | str:
    named = namespace_from_path(path)
    if not named:
        return "The path of a namespace is \\\\domain\\name or \\\\server\\name"
    server, namespace = named
    address = resolve(server)
    if not address:
        return "The name of the domain or server cannot be resolved: check Advanced settings > Network and DNS"
    import smbclient
    from smbclient._pool import dfs_request, get_smb_tree
    from smbprotocol.dfs import ReferralEntry

    smbclient.ClientConfig(skip_dfs=True)
    try:
        tree, _ = get_smb_tree(f"\\\\{address}\\IPC$", username=username, password=password, port=port, connection_timeout=15)
        entry = ReferralEntry(dfs_request(tree, f"\\\\{server}\\{namespace}"))
        targets = [_clean_target(target.target_path) for target in entry.target_list]
    except Exception:
        return "This path is not a DFS namespace, or the account cannot read it"
    finally:
        try:
            smbclient.reset_connection_cache()
        except Exception:
            pass
    if not targets:
        return "This namespace has no root server"
    root_host = [part for part in targets[0].split("\\") if part][0]
    return root_host, namespace


def disk_shares(listing: str) -> list[str]:
    shares = []
    for line in listing.splitlines():
        parts = line.split("|")
        if len(parts) >= 2 and parts[0] == "Disk":
            name = parts[1].strip()
            if name and name.upper() not in _SYSTEM_SHARES and not re.fullmatch(r"[A-Za-z]\$", name):
                shares.append(name)
    return shares


def namespace_from_path(path: str) -> tuple[str, str] | None:
    """(server or domain, namespace) of \\\\corp.local\\brest or \\\\DFS01\\lorient."""
    parts = [part for part in str(path or "").replace("/", "\\").split("\\") if part]
    return (parts[0], parts[1]) if len(parts) >= 2 else None


def read_dfs_namespaces(params: dict[str, Any]):
    host = str(params.get("host") or "").strip().strip("\\/")
    path = str(params.get("path") or "").strip()
    if path:
        # \\corp.local\brest: the domain answers which server holds the namespace, then that server is read
        located = _root_server(path, username=str(params.get("username") or ""), password=str(params.get("password") or ""),
                               port=int(params.get("port") or 445))
        if isinstance(located, str):
            return False, located, {"path": path, "failure_code": "DFS_NAMESPACE_NOT_FOUND"}
        host, namespace = located
        params = {**params, "host": host, "namespaces": [namespace]}
    username = str(params.get("username") or "").strip()
    password = str(params.get("password") or "")
    port = int(params.get("port") or 445)
    domain = str(params.get("domain") or "").strip().lower().strip(".")
    wanted = {str(name).lower() for name in (params.get("namespaces") or [])}
    max_links = max(1, min(int(params.get("max_links") or 5000), 20000))
    details: dict[str, Any] = {"server": host, "domain": domain or None}
    if not host or not username or not password:
        return False, "Missing server or account", {**details, "failure_code": "DFS_INPUT_MISSING"}
    address = resolve(host)
    if not address:
        return False, "The name of the DFS server cannot be resolved: check its domain in Advanced settings > Network and DNS", {
            **details, "failure_code": "DFS_DNS_FAILED",
        }
    details["address"] = address

    listing = run_samba(["smbclient", "-L", f"//{host}", "-p", str(port), "-m", "SMB3", "-g"], username=username,
                        password=password, capture_output=True, timeout=30)
    output = (listing.stdout or b"").decode(errors="ignore") + (listing.stderr or b"").decode(errors="ignore")
    if "NT_STATUS_LOGON_FAILURE" in output or "NT_STATUS_ACCESS_DENIED" in output:
        return False, "The DFS server refused the account", {**details, "failure_code": "DFS_AUTH_FAILED"}
    shares = disk_shares(output)

    import smbclient
    from smbclient._pool import dfs_request, get_smb_tree
    from smbprotocol.dfs import ReferralEntry

    smbclient.ClientConfig(skip_dfs=True)
    try:
        tree, _ = get_smb_tree(f"\\\\{address}\\IPC$", username=username, password=password, port=port, connection_timeout=15)

        def referral(path: str) -> tuple[bool, list[str]] | None:
            try:
                entry = ReferralEntry(dfs_request(tree, path))
            except Exception:
                return None
            return entry.is_root, [_clean_target(target.target_path) for target in entry.target_list]

        def list_dir(path: str):
            for item in smbclient.scandir(path, username=username, password=password, port=port):
                attributes = int(item.smb_info.file_attributes)
                yield item.name, item.is_dir(), bool(attributes & _REPARSE_POINT)

        namespaces = []
        for share in shares:
            if wanted and share.lower() not in wanted:
                continue  # a path was given: only that namespace
            root = referral(f"\\\\{host}\\{share}")
            if not root or not root[0]:
                continue  # an ordinary share, not a DFS root
            in_domain = referral(f"\\\\{domain}\\{share}") if domain else None
            path = f"\\\\{domain}\\{share}" if in_domain and in_domain[0] else f"\\\\{host}\\{share}"
            entry: dict[str, Any] = {
                "name": share,
                "path": path,
                "type": "domain" if in_domain and in_domain[0] else "standalone",
                "root_targets": root[1],
                "links": [],
                "error": None,
            }
            try:
                for rel in walk_links(f"\\\\{address}\\{share}", list_dir, max_links=max_links):
                    answer = referral(f"{path}\\{rel}") or referral(f"\\\\{host}\\{share}\\{rel}")
                    entry["links"].append({"path": rel, "targets": answer[1] if answer else []})
            except Exception as exc:
                entry["error"] = str(exc)[:300]
            namespaces.append(entry)
    except Exception as exc:
        return False, f"The DFS server could not be read: {str(exc)[:200]}", {**details, "failure_code": "DFS_READ_FAILED"}
    finally:
        try:
            smbclient.reset_connection_cache()
        except Exception:
            pass
    if wanted and not namespaces:
        return False, "This namespace was not found on its server.", {**details, "failure_code": "DFS_NAMESPACE_NOT_FOUND"}
    return True, "DFS namespaces read", {**details, "namespaces": namespaces}
