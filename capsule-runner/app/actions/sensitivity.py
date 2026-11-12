"""Sensitivity scan of a governed folder: passwords, keys, password vaults, personal and bank data, risky files.

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

# 3: personal data (social security number), bank data (IBAN, card), backups and databases, mailboxes, programs
RULES_VERSION = 3
MAX_LISTED = 300_000
# Files whose content is read in one pass (the next pass, queued by the core, goes on)
MAX_READ_FILES = 1000
MAX_FILE_BYTES = 1024 * 1024
MAX_READ_BYTES = 50 * 1024 * 1024
MAX_FINDINGS = 100
# Files fetched per smbclient call (each « get » line is up to ~600 bytes; an argument holds ~128 KB)
GET_BATCH = 100

# By the name alone: what it is says enough
NAME_RULES: list[tuple[str, str, re.Pattern[str]]] = [
    ("password_vault", "Password vault", re.compile(r"\.(kdbx|kdb|psafe3|opvault|agilekeychain|1pif)$")),
    ("private_key", "Private key or certificate with key", re.compile(r"(^id_(rsa|dsa|ecdsa|ed25519)$|\.(ppk|pfx|p12|jks|keystore)$)")),
    ("credentials_file", "File named after passwords",
     re.compile(r"(passwords?|passwd|pwd|mots?[ _.-]?de[ _.-]?passe|mdp|credentials?|identifiants?|secrets?|logins?|kennw[oö]rt|passw[oö]rt|contrase[nñ]as?"
                r"|codes?[ _.-]?(d[ _.'’-]?)?acc[eè]s|comptes?[ _.-]?(admin|de[ _.-]?service|service)|keepass|bitwarden|lastpass|1password)"
                r"[^\\/]*\.(txt|xlsx?|xlsm|docx?|csv|ods|odt|json|ini|cfg|conf|md|rtf|one|pdf)$")),
    ("credentials_file", "Stored credentials", re.compile(r"^(\.git-credentials|\.netrc|_netrc|\.pgpass|\.my\.cnf|unattend\.xml|autounattend\.xml|sysprep\.inf)$")),
    # Files that should not sit in a data share: copies of whole databases or machines, mailboxes, programs
    ("backup_database", "Backup, database or disk image",
     re.compile(r"\.(bak|bkp|mdb|accdb|sqlite3?|db3|sdf|dump|dmp|vhdx?|vmdk|ova|ovf)$")),
    ("mailbox", "Mailbox file", re.compile(r"\.(pst|ost|mbox|olm)$")),
    ("executable", "Program or script", re.compile(r"\.(exe|msi|com|scr|pif|bat|cmd|ps1|vbs|vbe|wsf|hta|jar)$")),
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


def _digits(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z]", "", value)


def _iban_ok(value: str) -> bool:
    """Check digits of an IBAN (ISO 13616: mod 97 = 1)."""
    raw = _digits(value).upper()
    if not 15 <= len(raw) <= 34:
        return False
    moved = raw[4:] + raw[:4]
    number = "".join(str(int(char, 36)) for char in moved)
    return int(number) % 97 == 1


def _luhn_ok(value: str) -> bool:
    """A payment card number: 13 to 19 digits, a known first digit, the Luhn checksum."""
    raw = _digits(value)
    if not raw.isdigit() or not 13 <= len(raw) <= 19 or raw[0] not in "3456" or len(set(raw)) < 3:
        return False
    total = 0
    for index, char in enumerate(reversed(raw)):
        digit = int(char)
        if index % 2:
            digit = digit * 2 - 9 if digit > 4 else digit * 2
        total += digit
    return total % 10 == 0


def _nir_ok(value: str) -> bool:
    """French social security number (NIR): 13 characters and a key, 97 - (number mod 97); Corsica 2A / 2B."""
    raw = _digits(value).upper()
    if len(raw) != 15:
        return False
    body, key = raw[:13], raw[13:]
    body = body.replace("2A", "19").replace("2B", "18")
    return body.isdigit() and key.isdigit() and 97 - int(body) % 97 == int(key)


# (category, label, pattern, check, characters kept in the excerpt): numbers found in a text, kept only when their
# own checksum holds. The excerpt keeps the country of an IBAN (FR76) and the network of a card (4970), nothing of a
# social security number (its first digits say the sex and the year of birth).
DATA_RULES: list[tuple[str, str, re.Pattern[str], object, int]] = [
    ("bank_data", "IBAN", re.compile(r"\b([A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,4})?)\b"), _iban_ok, 4),
    ("bank_data", "Payment card number", re.compile(r"(?<![\d-])((?:\d[ -]?){12,18}\d)(?![\d-])"), _luhn_ok, 4),
    ("personal_data", "Social security number",
     re.compile(r"\b([12] ?\d{2} ?(?:0[1-9]|1[0-2]|[2-9]\d) ?(?:\d{2}|2A|2B) ?\d{3} ?\d{3} ?\d{2})\b"), _nir_ok, 0),
]


def _data_hits(line: str) -> list[tuple[str, str, str, int]]:
    """(category, label, value, kept) of every valid number of the line, in the order of the rules."""
    hits = []
    for category, label, pattern, check, kept in DATA_RULES:
        for match in pattern.finditer(line):
            if check(match.group(1)):  # type: ignore[operator]
                hits.append((category, label, match.group(1), kept))
    return hits


def _mask_data(text: str, hits: list[tuple[str, str, str, int]]) -> str:
    """Every number found masked in the excerpt, whatever rule flagged the line."""
    for _category, _label, value, kept in sorted(hits, key=lambda hit: -len(hit[2])):
        text = text.replace(value, value[:kept] + "•" * 6)
    return text


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
        found = False
        hits = _data_hits(line)
        for category, label, pattern, group in CONTENT_RULES:
            match = pattern.search(line)
            if not match:
                continue
            secret = match.group(group)
            if group and _PLACEHOLDER.match(secret.strip()):
                continue
            excerpt = line.strip()
            excerpt = excerpt.replace(secret, _mask(secret)) if group else excerpt
            out.append({"path": path, "category": category, "rule": label, "line": number, "excerpt": _mask_data(excerpt, hits)[:160]})
            found = True
            break
        if not found and hits:
            # The line without the numbers: what kind of data and where, never the data itself
            category, label, _value, _kept = hits[0]
            out.append({"path": path, "category": category, "rule": label, "line": number, "excerpt": _mask_data(line.strip(), hits)[:160]})
        if len(out) >= limit:
            break
    return out


def _counts(findings: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in findings:
        counts[item["category"]] = counts.get(item["category"], 0) + 1
    return counts


def _listing_smb(base_cmd: list[str], rel_path: str, username: str, password: str, timeout: int) -> tuple[list[tuple[str, int, float | None]], bool]:
    """Every file of the folder through SMB (path, size, change time), read as it streams."""
    from app.actions.smb import _modified
    from app.shared.samba_auth import stream_samba

    pattern = f"{rel_path}\\*" if rel_path else "*"
    base_parts = [part for part in rel_path.replace("/", "\\").split("\\") if part]
    folder: list[str] = list(base_parts)
    files: list[tuple[str, int, float | None]] = []
    errors: list[str] = []
    seen = 0
    truncated = False
    with stream_samba([*base_cmd, "-c", f'recurse ON; ls "{pattern}"'], username=username, password=password, timeout=timeout) as lines:
        for line in lines:
            if line.startswith("\\"):
                folder = [part for part in line.strip().split("\\") if part]
                continue
            match = _LS_ENTRY.match(line.rstrip())
            if not match:
                if "NT_STATUS_" in line:
                    errors.append(line)
                continue
            if match["name"] in {".", ".."} or "D" in match["attr"]:
                continue
            seen += 1
            if seen > MAX_LISTED:
                truncated = True
                break
            files.append(("\\".join([*folder, match["name"]]), int(match["size"]), _modified(match["date"])))
    if not files and errors:
        raise RuntimeError(errors[-1])
    return files, truncated


def _after(stamp: float | None, path: str, since: float | None, cursor: str) -> bool:
    """Changed since the cursor of the last scan: (change time, path) after (since, cursor)."""
    if since is None:
        return True
    if stamp is None:
        return False
    return stamp > since or (stamp == since and path > cursor)


def scan_smb_sensitivity(params: dict):
    """Incremental: the names of all the files are checked at each scan (cheap); the content only of the text files
    changed since the cursor of the last scan, the oldest first, within the budget of one scan. The next scan starts
    where this one stopped, until every changed file has been read; then the cursor is the start of the scan.
    The files flagged before that are gone are reported, so that the core forgets them."""
    host = params["host"]
    share = params["share"]
    rel_path = str(params.get("path") or "").strip().strip("/\\").replace("/", "\\")
    username = params["username"]
    password = params["password"]
    port = int(params.get("port", 445))
    timeout = int(params.get("timeout", 300))
    target_label = f"\\\\{host}\\{share}" + (f"\\{rel_path}" if rel_path else "")
    base_cmd = ["smbclient", f"//{host}/{share}", "-m", "SMB3", "-p", str(port)]
    started = datetime.now(timezone.utc)
    since_iso = params.get("since") if params.get("rules_version") == RULES_VERSION else None
    since = datetime.fromisoformat(str(since_iso).replace("Z", "+00:00")).timestamp() if since_iso else None
    cursor = str(params.get("cursor_path") or "") if since is not None else ""
    known = [str(path) for path in (params.get("known_paths") or [])][:200]

    method = "smb"
    fallback_reason = None
    name_hits: list[str] = []
    candidates: list[tuple[str, int, float | None]] = []
    pending_total = 0
    gone: list[str] = []
    files_listed = 0
    truncated = False
    server = None
    if params.get("server_name"):
        from app.shared.server_scan import ServerScanError, sensitivity_listing
        from app.shared.winrm import WinRMError

        try:
            server = sensitivity_listing(
                share=share, path=rel_path, name_patterns=[pattern.pattern for _c, _l, pattern in NAME_RULES],
                text_extensions=sorted(TEXT_EXTENSIONS), text_names=sorted(TEXT_NAMES), max_file_bytes=MAX_FILE_BYTES,
                since=since_iso if since is not None else None, cursor_path=cursor, known_paths=known, candidates=MAX_READ_FILES * 2,
                timeout=max(timeout, 600),
                connection={"host": host, "server_name": params.get("server_name"), "username": username, "password": password,
                            "domain": str(params.get("domain") or ""), "kdc_hint": params.get("kdc_host")})
        except (WinRMError, ServerScanError) as exc:
            fallback_reason = f"{getattr(exc, 'code', 'WINRM_FAILED')}: {getattr(exc, 'message', str(exc))}"[:300]
    if server is not None:
        method = "server"
        files_listed = int(server.get("files_listed") or 0)
        name_hits = [str(item["path"]) for item in server.get("name_hits") or []]
        for item in server.get("candidates") or []:
            stamp = datetime.fromisoformat(str(item["modified"]).replace("Z", "+00:00")).timestamp() if item.get("modified") else None
            candidates.append((str(item["path"]), int(item.get("size") or 0), stamp))
        pending_total = int(server.get("pending_total") or 0)
        gone = [str(path) for path in server.get("gone_paths") or []]
    else:
        try:
            files, truncated = _listing_smb(base_cmd, rel_path, username, password, timeout)
        except TimeoutError:
            return False, f"Listing of {target_label} timed out", {"failure_code": "CAPSULE_TIMEOUT", "retryable": False}
        except RuntimeError as exc:
            return False, f"Listing of {target_label} failed: {str(exc)[-300:]}", {"failure_code": _classify_smb_error(str(exc))}
        files_listed = len(files)
        name_hits = [path for path, _size, _stamp in files]
        changed = sorted(((path, size, stamp) for path, size, stamp in files if is_text_candidate(path, size) and _after(stamp, path, since, cursor)),
                         key=lambda item: (item[2] or 0, item[0]))
        pending_total = len(changed)
        candidates = changed
        present = {path.lower() for path, _size, _stamp in files}
        gone = [] if truncated else [path for path in known if path.lower() not in present]

    findings: list[dict] = []
    for path in name_hits:
        findings.extend(name_findings(path))

    chosen: list[tuple[str, int, float | None]] = []
    total = 0
    for item in candidates:
        if len(chosen) >= MAX_READ_FILES or total + item[1] > MAX_READ_BYTES:
            break
        chosen.append(item)
        total += item[1]

    files_read = 0
    bytes_read = 0
    read_paths: list[str] = []
    workdir = tempfile.mkdtemp(prefix="b2s-sens-")
    try:
        if chosen:
            # By batches: one smbclient argument holds at most ~128 KB (E2BIG « Argument list too long » beyond)
            items = list(enumerate(chosen))
            for start in range(0, len(items), GET_BATCH):
                gets = "; ".join(f'get "{path}" "{os.path.join(workdir, f"{index:05d}")}"' for index, (path, _size, _stamp) in items[start:start + GET_BATCH])
                try:
                    run_samba([*base_cmd, "-c", f"prompt OFF; {gets}"], username=username, password=password,
                              capture_output=True, timeout=timeout, check=False)
                except subprocess.TimeoutExpired:
                    truncated = True
                    break
            for index, (path, _size, _stamp) in enumerate(chosen):
                local = os.path.join(workdir, f"{index:05d}")
                if not os.path.exists(local):
                    continue
                with open(local, "rb") as handle:
                    raw = handle.read(MAX_FILE_BYTES)
                files_read += 1
                bytes_read += len(raw)
                read_paths.append(path)
                if b"\x00" in raw[:1024] and not raw.startswith((b"\xff\xfe", b"\xfe\xff")):
                    continue  # binary
                findings.extend(content_findings(path, _decode(raw)))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    # Where the next scan starts: after the last file read, or at the start of this one when every changed file was read
    complete = len(read_paths) >= pending_total and not truncated
    last = chosen[len(read_paths) - 1] if read_paths else None
    if complete or last is None or last[2] is None:
        next_since, next_cursor = (started.isoformat() if complete else since_iso), ("" if complete else cursor)
    else:
        next_since, next_cursor = datetime.fromtimestamp(last[2], tz=timezone.utc).isoformat(), last[0]

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
            "scanned_at": started.isoformat(),
            "target": target_label,
            "method": method,
            "fallback_reason": fallback_reason,
            "files_listed": files_listed,
            "files_read": files_read,
            "bytes_read": bytes_read,
            "truncated": truncated,
            "counts": _counts(findings),
            "files_flagged": len({item["path"].lower() for item in findings}),
            "findings": findings[:MAX_FINDINGS],
            "incremental": {"full": since is None, "since": since_iso if since is not None else None, "next_since": next_since,
                            "next_cursor": next_cursor, "complete": complete, "pending": max(0, pending_total - len(read_paths)),
                            "read_paths": read_paths, "gone_paths": gone},
        }
    }
    flagged = details["sensitivity"]["files_flagged"]
    return True, (f"{flagged} sensitive file(s) in {target_label}" if flagged else f"Nothing sensitive found in {target_label}"), details
