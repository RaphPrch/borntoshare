"""Sensitivity scan of a governed folder: are there passwords, keys or password vaults stored in it?

Read only. One recursive listing of the folder (smbclient), then the small text files that may hold a secret
are copied in one SMB session into a private temporary directory, read, and deleted. What is kept is the path
of the file, the rule that matched, the line number and a masked excerpt: never the secret itself.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone

from app.actions.smb import _LS_ENTRY, _classify_smb_error, run_samba

RULES_VERSION = 2
MAX_LISTED = 300_000
MAX_READ_FILES = 300
MAX_FILE_BYTES = 1024 * 1024
MAX_READ_BYTES = 50 * 1024 * 1024
MAX_FINDINGS = 100

# By the name alone: what it is says enough
NAME_RULES: list[tuple[str, str, re.Pattern[str]]] = [
    ("password_vault", "Password vault", re.compile(r"\.(kdbx|kdb|psafe3|opvault|agilekeychain|1pif)$")),
    ("private_key", "Private key or certificate with key", re.compile(r"(^id_(rsa|dsa|ecdsa|ed25519)$|\.(ppk|pfx|p12|jks|keystore)$)")),
    ("credentials_file", "File named after passwords",
     re.compile(r"(passwords?|passwd|pwd|mots?[ _.-]?de[ _.-]?passe|mdp|credentials?|identifiants?|secrets?|logins?|kennw[oö]rt|passw[oö]rt|contrase[nñ]as?"
                r"|codes?[ _.-]?(d[ _.'’-]?)?acc[eè]s|comptes?[ _.-]?(admin|de[ _.-]?service|service)|keepass|bitwarden|lastpass|1password)"
                r"[^\\/]*\.(txt|xlsx?|xlsm|docx?|csv|ods|odt|json|ini|cfg|conf|md|rtf|one|pdf)$")),
    ("credentials_file", "Stored credentials", re.compile(r"^(\.git-credentials|\.netrc|_netrc|\.pgpass|\.my\.cnf|unattend\.xml|autounattend\.xml|sysprep\.inf)$")),
]

# Read when small: the files where a secret is typically written in clear
TEXT_EXTENSIONS = {
    "txt", "ini", "cfg", "conf", "config", "xml", "json", "yml", "yaml", "env", "ps1", "psm1", "psd1", "bat", "cmd",
    "sh", "vbs", "py", "properties", "sql", "md", "csv", "inf", "reg", "php", "rdp", "pem", "key", "toml",
}
TEXT_NAMES = {".env", ".netrc", "_netrc", ".pgpass", ".git-credentials", ".my.cnf"}

_PLACEHOLDER = re.compile(r"^(\*+|x+|\.+|changeme|password|motdepasse|<.*>|\$\{.*|%.*%|\{\{.*|null|none|true|false)$", re.IGNORECASE)
CONTENT_RULES: list[tuple[str, str, re.Pattern[str], int]] = [
    # (category, label, pattern, group holding the secret; 0 = the whole match)
    ("private_key", "Private key", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----"), 0),
    ("cloud_key", "AWS access key", re.compile(r"\b(AKIA[0-9A-Z]{16})\b"), 1),
    ("cloud_key", "API key or token",
     re.compile(r"(?i)\b(?:api[_-]?key|secret[_-]?key|client[_-]?secret|access[_-]?token|auth[_-]?token)\b\s*[:=]\s*['\"]?([A-Za-z0-9_\-+/=.]{16,})"), 1),
    ("password", "Password in clear",
     re.compile(r"(?i)\b(?:password|passwd|pwd|pass|mot\s?de\s?passe|mdp|kennwort|passwort|contrase(?:n|ñ)a|senha)\b\s*[:=]\s*['\"]?([^\s'\";<>]{4,})"), 1),
    ("password", "Password written in a script",
     re.compile(r"(?i)ConvertTo-SecureString\s+(?:-String\s+)?['\"]([^'\"]{4,})['\"]\s+-AsPlainText"), 1),
    ("password", "Password on a net use / net user command",
     re.compile(r"(?i)\bnet\s+(?:use\s+(?:(?:[a-z]:|\*)\s+)?\\\\\S+|user\s+\S+)\s+([^\s/*]{4,})\s+/(?:user:|add\b)"), 1),
    ("password", "Password in a Windows answer file",
     re.compile(r"(?i)<(?:AdministratorPassword|Password)>\s*<Value>([^<]{4,})</Value>"), 1),
]


def list_files(output: str, base: str = "", max_entries: int = MAX_LISTED) -> tuple[list[tuple[str, int]], bool]:
    """Files of a smbclient « recurse ON; ls » listing: (path relative to the share, size); truncated or not."""
    base_parts = [part for part in base.replace("/", "\\").split("\\") if part]
    folder: list[str] = list(base_parts)
    files: list[tuple[str, int]] = []
    seen = 0
    for line in output.splitlines():
        if line.startswith("\\"):
            folder = [part for part in line.strip().split("\\") if part]
            continue
        match = _LS_ENTRY.match(line.rstrip())
        if not match or match["name"] in {".", ".."}:
            continue
        seen += 1
        if seen > max_entries:
            return files, True
        if "D" in match["attr"]:
            continue
        files.append(("\\".join([*folder, match["name"]]), int(match["size"])))
    return files, False


def _extension(name: str) -> str:
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def name_findings(path: str) -> list[dict]:
    name = path.rsplit("\\", 1)[-1].lower()
    for category, label, pattern in NAME_RULES:
        if pattern.search(name):
            return [{"path": path, "category": category, "rule": label, "line": None, "excerpt": None}]
    return []


def is_text_candidate(path: str, size: int) -> bool:
    name = path.rsplit("\\", 1)[-1].lower()
    return 0 < size <= MAX_FILE_BYTES and (name in TEXT_NAMES or _extension(name) in TEXT_EXTENSIONS)


def _mask(secret: str) -> str:
    return (secret[:1] + "•" * 6) if len(secret) > 1 else "•" * 6


def _decode(raw: bytes) -> str:
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16", errors="ignore")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1", errors="ignore")


def content_findings(path: str, text: str, limit: int = 5) -> list[dict]:
    """Secrets written in a text: masked excerpt and line number, at most `limit` per file."""
    out: list[dict] = []
    for number, line in enumerate(text.splitlines(), start=1):
        for category, label, pattern, group in CONTENT_RULES:
            match = pattern.search(line)
            if not match:
                continue
            secret = match.group(group)
            if group and _PLACEHOLDER.match(secret.strip()):
                continue
            excerpt = line.strip()
            excerpt = excerpt.replace(secret, _mask(secret)) if group else excerpt
            out.append({"path": path, "category": category, "rule": label, "line": number, "excerpt": excerpt[:160]})
            break
        if len(out) >= limit:
            break
    return out


def _counts(findings: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in findings:
        counts[item["category"]] = counts.get(item["category"], 0) + 1
    return counts


def scan_smb_sensitivity(params: dict):
    host = params["host"]
    share = params["share"]
    rel_path = str(params.get("path") or "").strip().strip("/\\").replace("/", "\\")
    username = params["username"]
    password = params["password"]
    port = int(params.get("port", 445))
    timeout = int(params.get("timeout", 300))
    target_label = f"\\\\{host}\\{share}" + (f"\\{rel_path}" if rel_path else "")
    base_cmd = ["smbclient", f"//{host}/{share}", "-m", "SMB3", "-p", str(port)]

    pattern = f"{rel_path}\\*" if rel_path else "*"
    try:
        listing = run_samba([*base_cmd, "-c", f'recurse ON; ls "{pattern}"'], username=username, password=password,
                            capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return False, f"Listing of {target_label} timed out", {"failure_code": "CAPSULE_TIMEOUT", "retryable": False}
    output = ((listing.stdout or b"") + b"\n" + (listing.stderr or b"")).decode(errors="ignore")
    if listing.returncode != 0 and "NT_STATUS_" in output and not _LS_ENTRY.search(output):
        return False, f"Listing of {target_label} failed: {output.strip()[-300:]}", {"failure_code": _classify_smb_error(output)}

    files, truncated = list_files(output, base=rel_path)
    findings: list[dict] = []
    for path, _size in files:
        findings.extend(name_findings(path))

    candidates = [(path, size) for path, size in files if is_text_candidate(path, size)]
    chosen: list[tuple[str, int]] = []
    total = 0
    for path, size in candidates:
        if len(chosen) >= MAX_READ_FILES or total + size > MAX_READ_BYTES:
            truncated = True
            break
        chosen.append((path, size))
        total += size

    files_read = 0
    bytes_read = 0
    workdir = tempfile.mkdtemp(prefix="b2s-sens-")
    try:
        if chosen:
            gets = "; ".join(f'get "{path}" "{os.path.join(workdir, f"{index:05d}")}"' for index, (path, _size) in enumerate(chosen))
            try:
                run_samba([*base_cmd, "-c", f"prompt OFF; {gets}"], username=username, password=password,
                          capture_output=True, timeout=timeout, check=False)
            except subprocess.TimeoutExpired:
                truncated = True
            for index, (path, _size) in enumerate(chosen):
                local = os.path.join(workdir, f"{index:05d}")
                if not os.path.exists(local):
                    continue
                with open(local, "rb") as handle:
                    raw = handle.read(MAX_FILE_BYTES)
                files_read += 1
                bytes_read += len(raw)
                if b"\x00" in raw[:1024] and not raw.startswith((b"\xff\xfe", b"\xfe\xff")):
                    continue  # binary
                findings.extend(content_findings(path, _decode(raw)))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    # A file found by its name and by its content counts once per category
    unique: dict[tuple[str, str], dict] = {}
    for item in findings:
        key = (item["path"].lower(), item["category"])
        if key not in unique or (unique[key]["line"] is None and item["line"] is not None):
            unique[key] = item
    findings = list(unique.values())
    details = {
        "sensitivity": {
            "rules_version": RULES_VERSION,
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "target": target_label,
            "files_listed": len(files),
            "files_read": files_read,
            "bytes_read": bytes_read,
            "truncated": truncated,
            "counts": _counts(findings),
            "files_flagged": len({item["path"].lower() for item in findings}),
            "findings": findings[:MAX_FINDINGS],
        }
    }
    flagged = details["sensitivity"]["files_flagged"]
    return True, (f"{flagged} sensitive file(s) in {target_label}" if flagged else f"Nothing sensitive found in {target_label}"), details
