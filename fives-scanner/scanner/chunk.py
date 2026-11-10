"""PowerShell run on the file server for the scanner: the pieces of a folder, then the walk of one piece.

The walk is the one of the worker of the core (app.shared.server_scan, the same code, copied into the image), with:
- the process of the session at a low priority (BelowNormal): the users of the file server go first;
- one first-level sub-folder at a time (recurse), or only the files right in the folder (key "").
"""
from __future__ import annotations

import json
from typing import Any

from app.shared import server_scan
from app.shared.winrm import run_powershell

_PRIORITY = "try { [System.Diagnostics.Process]::GetCurrentProcess().PriorityClass = 'BelowNormal' } catch { }\n"

# The pieces of the folder and, in the same session, the change journal of its volume
_LIST = server_scan._COMMON + _PRIORITY + r"""
$dirs = @([System.IO.DirectoryInfo]::new($local).EnumerateDirectories() | Where-Object { ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0 } | ForEach-Object { $_.Name })
$p | Add-Member -NotePropertyName volume -NotePropertyValue ([IO.Path]::GetPathRoot($local).TrimEnd('\')) -Force
$p | Add-Member -NotePropertyName under -NotePropertyValue $local -Force
__USN__
# $listing, not $r: the walk of each piece (in the same session for a full scan) uses $r
$listing = [ordered]@{}
$listing.local_path = $local; $listing.volume = $p.volume; $listing.chunks = @($dirs | ForEach-Object { $_ }); $listing.journal = $journal
$listing | ConvertTo-Json -Compress -Depth 6
"""

# The walk of several pieces in one session, within a time budget (the next call goes on with the rest)
_BODY_START = "$junk = [regex]::new($p.junk_pattern, 'IgnoreCase')"
assert _BODY_START in server_scan._MEASURE and "Send-Result $r" in server_scan._MEASURE, "the measure script of the worker changed: review chunk.py"
_BODY = server_scan._MEASURE[server_scan._MEASURE.index(_BODY_START):]
_BODY = _BODY.replace(
    "Walk $local $onFile $onDir",
    "if ($recurse) { Walk $local $onFile $onDir } else { foreach ($f in [System.IO.DirectoryInfo]::new($local).EnumerateFiles()) { & $onFile $f } }",
).replace("Send-Result $r", "$out.Add([pscustomobject]@{ key = $key; stats = $r })")
assert "if ($recurse)" in _BODY and "$out.Add(" in _BODY
# The pieces of $p.keys walked one after the other within $p.budget_seconds (at least one): $out
_LOOP = r"""
$parent = $local
$out = New-Object 'System.Collections.Generic.List[object]'
$budget = [Diagnostics.Stopwatch]::StartNew()
foreach ($key in @($p.keys)) {
  if ($out.Count -gt 0 -and $budget.Elapsed.TotalSeconds -gt [int]$p.budget_seconds) { break }
  $local = if ($key) { Join-Path $parent $key } else { $parent }
  $recurse = [bool]$key
  $state = @{ denied = 0; last = [DateTime]::MinValue; listed = 0; pending = 0 }
  $watch = [Diagnostics.Stopwatch]::StartNew()
""" + _BODY + r"""
}
"""
_WALK = server_scan._COMMON + _PRIORITY + _LOOP + r"""
[ordered]@{ chunks = @($out | ForEach-Object { $_ }) } | ConvertTo-Json -Compress -Depth 10
"""
# First scan or full walk due: the pieces, the journal (its position only) and the walk, in one session
_FULL = _LIST.replace("$listing | ConvertTo-Json -Compress -Depth 6\n", "").replace(
    "$p | Add-Member -NotePropertyName under",
    "$p | Add-Member -NotePropertyName keys -NotePropertyValue (@('') + @($dirs)) -Force\n$p | Add-Member -NotePropertyName under",
) + _LOOP + r"""
$listing.walked = @($out | ForEach-Object { $_ })
$listing | ConvertTo-Json -Compress -Depth 10
"""
assert "$listing.walked" in _FULL and "$listing | ConvertTo-Json -Compress -Depth 6" not in _FULL


class ScanError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _run(template: str, params: dict[str, Any], connection: dict[str, Any], timeout: int) -> dict[str, Any]:
    answer = run_powershell(script=template.replace("__PARAMS__", json.dumps(params, ensure_ascii=True)), timeout=timeout, **connection)
    lines = [line for line in answer["output"].splitlines() if line.strip().startswith("{")]
    if not lines:
        raise ScanError("SCAN_NO_ANSWER", str((answer.get("errors") or ["The server gave no answer"])[0])[:400])
    result = json.loads(lines[-1])
    if result.get("error"):
        raise ScanError(str(result["error"]), str(result.get("message") or result["error"])[:400])
    return result


def full_scan(*, share: str, path: str, connection: dict[str, Any], junk_pattern: str, hash_files_max: int, budget_seconds: int = 120) -> dict[str, Any]:
    """Pieces, journal position and walk of the pieces within the budget, in one session (the rest: walk_chunks)."""
    from scanner import usn as journal

    template = _FULL.replace("__USN__", journal.fragment())
    return _run(template, {"share": share, "path": path, "since_usn": None, "journal_id": None, "max_folders": 50000, "budget_seconds": budget_seconds,
                           "junk_pattern": junk_pattern, "dup_min_bytes": 64 * 1024, "fingerprint_min_bytes": 1024 * 1024, "fingerprints_max": 300,
                           "hash_files_max": hash_files_max}, connection, 6 * 3600)


def list_chunks(*, share: str, path: str, connection: dict[str, Any], since_usn: int | None, journal_id: str | None) -> dict[str, Any]:
    from scanner import usn as journal

    template = _LIST.replace("__USN__", journal.fragment())
    return _run(template, {"share": share, "path": path, "since_usn": since_usn, "journal_id": journal_id, "max_folders": 50000}, connection, 900)


def walk_chunks(*, share: str, path: str, keys: list[str], connection: dict[str, Any], junk_pattern: str, hash_files_max: int,
                budget_seconds: int = 120, timeout: int = 6 * 3600) -> list[dict[str, Any]]:
    """Walk these pieces (in order) in one session; returns those done within the budget (at least one)."""
    result = _run(_WALK, {"share": share, "path": path, "keys": keys, "budget_seconds": budget_seconds, "junk_pattern": junk_pattern,
                          "dup_min_bytes": 64 * 1024, "fingerprint_min_bytes": 1024 * 1024, "fingerprints_max": 300,
                          "hash_files_max": hash_files_max}, connection, timeout)
    return list(result.get("chunks") or [])
