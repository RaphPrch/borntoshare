"""Quotas of the governed folders, on the Windows file server itself (FSRM, File Server Resource Manager).

The folder \\\\server\\share\\path becomes its local path on the server (Get-SmbShare), then:
- read:   the FSRM quota of this path (limit, use, peak, hard or soft, warning thresholds), or none;
- set:    creates or changes it (New-FsrmQuota / Set-FsrmQuota) with a warning threshold that writes an event;
- remove: removes it (Remove-FsrmQuota).
Every operation answers the quota as it is after it, read again on the server.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict

from app.actions.folder import _rel_path
from app.shared.windows_names import share_name_error
from app.shared.winrm import WinRMError, run_powershell

logger = logging.getLogger(__name__)

OPERATIONS = {"read", "set", "remove"}
MIN_LIMIT = 1024 * 1024  # FSRM refuses less than 1 MB
MAX_LIMIT = 1024 ** 5  # 1 PB

# The parameters arrive as JSON in a single-quoted here-string: nothing in them is ever run as PowerShell
_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$p = @'
__PARAMS__
'@ | ConvertFrom-Json
function Send-Result($value) { $value | ConvertTo-Json -Compress -Depth 4 }
$share = Get-SmbShare -Name $p.share -ErrorAction SilentlyContinue
if (-not $share) { Send-Result @{ error = 'FSRM_SHARE_NOT_FOUND'; message = "No share $($p.share) on this server" }; return }
$local = $share.Path
if ($p.path) { $local = Join-Path $local $p.path }
if (-not (Test-Path -LiteralPath $local -PathType Container)) { Send-Result @{ error = 'FSRM_FOLDER_NOT_FOUND'; message = "No folder $local on this server"; local_path = $local }; return }
if (-not (Get-Command Get-FsrmQuota -ErrorAction SilentlyContinue)) {
  Send-Result @{ error = 'FSRM_NOT_INSTALLED'; message = 'The File Server Resource Manager role is not installed on this server'; local_path = $local }; return
}
$quota = Get-FsrmQuota -Path $local -ErrorAction SilentlyContinue
try {
  if ($p.op -eq 'set') {
    $body = 'BornToShare: [Quota Path] reached [Quota Threshold]% of its quota ([Quota Used MB] MB of [Quota Limit MB] MB).'
    $event = New-FsrmAction -Type Event -EventType Warning -Body $body
    $threshold = New-FsrmQuotaThreshold -Percentage ([int]$p.warn_percent) -Action @($event)
    $settings = @{ Path = $local; Size = [uint64]$p.limit_bytes; SoftLimit = [bool]$p.soft; Threshold = @($threshold); Description = [string]$p.description }
    if ($quota) { Set-FsrmQuota @settings } else { New-FsrmQuota @settings | Out-Null }
    $quota = Get-FsrmQuota -Path $local
  } elseif ($p.op -eq 'remove') {
    if ($quota) { Remove-FsrmQuota -Path $local -Confirm:$false }
    $quota = $null
  }
} catch {
  Send-Result @{ error = 'FSRM_REFUSED'; message = $_.Exception.Message; local_path = $local }; return
}
$result = @{ local_path = $local; exists = [bool]$quota }
if ($quota) {
  $result.limit_bytes = [uint64]$quota.Size
  $result.used_bytes = [uint64]$quota.Usage
  $result.peak_bytes = [uint64]$quota.PeakUsage
  $result.soft = [bool]$quota.SoftLimit
  $result.disabled = [bool]$quota.Disabled
  $result.status = [string]$quota.Status
  $result.thresholds = @($quota.Threshold | ForEach-Object { [int]$_.Percentage })
  $result.description = [string]$quota.Description
  $result.template = [string]$quota.Template
}
Send-Result $result
"""


def build_script(params: dict[str, Any]) -> str:
    return _SCRIPT.replace("__PARAMS__", json.dumps(params, ensure_ascii=True))


def parse_result(output: str) -> dict[str, Any]:
    lines = [line for line in str(output or "").splitlines() if line.strip().startswith("{")]
    if not lines:
        return {}
    try:
        value = json.loads(lines[-1])
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def folder_quota(params: Dict[str, Any]):
    """Read, set or remove the FSRM quota of a folder (operation: read | set | remove)."""
    host = str(params.get("host") or "").strip()
    share = str(params.get("share") or "").strip()
    path = _rel_path(params.get("path"))
    operation = str(params.get("operation") or "read").strip().lower()
    username = str(params.get("username") or "").strip()
    domain = str(params.get("domain") or "").strip()
    timeout = int(params.get("timeout_sec") or 60)
    details: dict[str, Any] = {"operation": "folder_quota", "quota_operation": operation, "target": {"host": host, "share": share, "path": path}}

    if operation not in OPERATIONS:
        return False, "Invalid quota operation", {**details, "failure_code": "QUOTA_OPERATION_INVALID"}
    if share_name_error(share):
        return False, "Invalid share name", {**details, "failure_code": "QUOTA_SHARE_INVALID"}
    request: dict[str, Any] = {"op": operation, "share": share, "path": path}
    if operation == "set":
        limit = int(params.get("limit_bytes") or 0)
        warn = int(params.get("warn_percent") or 85)
        if not MIN_LIMIT <= limit <= MAX_LIMIT:
            return False, "The quota must be between 1 MB and 1 PB", {**details, "failure_code": "QUOTA_LIMIT_INVALID"}
        if not 50 <= warn <= 100:
            return False, "The warning threshold must be between 50 and 100 %", {**details, "failure_code": "QUOTA_THRESHOLD_INVALID"}
        request.update({"limit_bytes": limit, "soft": bool(params.get("soft")), "warn_percent": warn,
                        "description": str(params.get("description") or "BornToShare")[:255]})
    try:
        answer = run_powershell(host=host, server_name=params.get("server_name"), username=username,
                                password=str(params.get("password") or ""), domain=domain, kdc_hint=params.get("kdc_host"),
                                script=build_script(request), timeout=timeout)
    except WinRMError as exc:
        return False, exc.message, {**details, "failure_code": exc.code, "hint": exc.hint}
    result = parse_result(answer["output"])
    if not result:
        message = (answer.get("errors") or ["The server gave no answer"])[0]
        return False, str(message)[:400], {**details, "failure_code": "FSRM_NO_ANSWER"}
    if result.get("error"):
        hint = None
        if result["error"] == "FSRM_NOT_INSTALLED":
            hint = "Install the role: Install-WindowsFeature FS-Resource-Manager -IncludeManagementTools"
        elif result["error"] == "FSRM_REFUSED" and re.search(r"(?i)not found|introuvable|non trouv", str(result.get("message") or "")):
            # Seen right after installing the role: the quota driver is not attached to the volume until a restart
            hint = "Restart the server once after installing FSRM (or: fltmc attach Quota C: then Restart-Service SrmSvc)"
        return False, str(result.get("message") or result["error"])[:400], {**details, "failure_code": str(result["error"]), "hint": hint,
                                                                             "local_path": result.get("local_path")}
    details["quota"] = result
    logger.info("Folder quota", extra={"operation": "folder_quota", "quota_operation": operation, "target_share": share, "target_path": path,
                                       "exists": bool(result.get("exists"))})
    verb = {"read": "read", "set": "set", "remove": "removed"}[operation]
    return True, f"Quota {verb} on {result.get('local_path')}", details


def read_folder_quota(params: Dict[str, Any]):
    return folder_quota({**params, "operation": "read"})


def apply_folder_quota(params: Dict[str, Any]):
    operation = str(params.get("operation") or "").strip().lower()
    if operation not in {"set", "remove"}:
        return False, "Invalid quota operation", {"operation": "folder_quota", "failure_code": "QUOTA_OPERATION_INVALID"}
    return folder_quota(params)
