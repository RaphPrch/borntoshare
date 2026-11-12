"""Walk of a governed folder ON the Windows file server (PowerShell over WinRM), instead of listing it through SMB.

The server reads its own disk and sends back only what BornToShare needs, never the millions of lines of a listing:
- measure:      size, files, sub-folders, weight of the first-level sub-folders, file types, age of the data, clutter,
                last change, probable duplicates (same size and same fingerprint) and the fingerprints of the biggest
                files (duplicates between folders are found by the core from them);
- sensitivity:  the files whose name matches a rule (the same patterns as the worker, checked again in Python), the
                text files changed since the cursor of the last scan (the oldest first, at most `candidates`), how many
                are still waiting, and which of the files flagged before are gone.

Fingerprint = SHA-256 of the size, the first 64 KiB and the last 64 KiB: two files with the same fingerprint are
duplicates with a very high probability, for 128 KiB read per file whatever its size. Bounded by a budget per scan.
"""
from __future__ import annotations

import json
from typing import Any

from app.shared.winrm import run_powershell

_COMMON = r"""
$ErrorActionPreference = 'Stop'
$p = @'
__PARAMS__
'@ | ConvertFrom-Json
function Send-Result($value) { $value | ConvertTo-Json -Compress -Depth 6 }
trap { Send-Result @{ error = 'SCAN_FAILED'; message = "$($_.Exception.Message) (line $($_.InvocationInfo.ScriptLineNumber): $($_.InvocationInfo.Line.Trim()))" }; break }
$share = Get-SmbShare -Name $p.share -ErrorAction SilentlyContinue
if (-not $share) { Send-Result @{ error = 'SCAN_SHARE_NOT_FOUND'; message = "No share $($p.share) on this server" }; return }
$base = $share.Path.TrimEnd('\')
$local = if ($p.path) { Join-Path $base $p.path } else { $base }
if (-not (Test-Path -LiteralPath $local -PathType Container)) { Send-Result @{ error = 'SCAN_FOLDER_NOT_FOUND'; message = "No folder $local on this server" }; return }
$cut = $base.Length + 1
$now = [DateTime]::UtcNow
$watch = [Diagnostics.Stopwatch]::StartNew()
$state = @{ denied = 0; last = [DateTime]::MinValue; listed = 0; pending = 0 }
# Depth-first walk that goes on when a folder cannot be read (counted in $denied)
function Walk([string]$root, [scriptblock]$onFile, [scriptblock]$onDir) {
  $stack = New-Object 'System.Collections.Generic.Stack[System.IO.DirectoryInfo]'
  $stack.Push([System.IO.DirectoryInfo]::new($root))
  while ($stack.Count) {
    $dir = $stack.Pop()
    try { $entries = $dir.EnumerateFileSystemInfos() } catch { $state.denied++; continue }
    try {
      foreach ($entry in $entries) {
        if ($entry -is [System.IO.DirectoryInfo]) {
          if (($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0) { $stack.Push($entry); & $onDir $entry }
        } else { & $onFile $entry }
      }
    } catch { $state.denied++ }
  }
}
function Fingerprint([string]$path, [long]$size) {
  $sha = [Security.Cryptography.SHA256]::Create()
  $stream = [IO.File]::Open($path, 'Open', 'Read', 'ReadWrite, Delete')
  try {
    $buffer = New-Object byte[] 65536
    $head = $stream.Read($buffer, 0, 65536)
    $sizeBytes = [BitConverter]::GetBytes($size)
    [void]$sha.TransformBlock($sizeBytes, 0, 8, $null, 0)
    [void]$sha.TransformBlock($buffer, 0, $head, $null, 0)
    if ($size -gt 131072) { [void]$stream.Seek(-65536, 'End'); $tail = $stream.Read($buffer, 0, 65536); [void]$sha.TransformFinalBlock($buffer, 0, $tail) }
    else { [void]$sha.TransformFinalBlock($buffer, 0, 0) }
    return ([BitConverter]::ToString($sha.Hash) -replace '-', '').ToLowerInvariant()
  } finally { $stream.Dispose(); $sha.Dispose() }
}
"""

_MEASURE = _COMMON + r"""
$junk = [regex]::new($p.junk_pattern, 'IgnoreCase')
$t = @{ bytes = [long]0; files = 0; folders = 0 }
$top = @{}; $types = @{}; $dirStats = @{}; $dirAcls = @{}
# Rights of each folder (5S scanner only, with_dirs): its entries « account|R/W/F|inherited » and whether its
# inheritance is broken (rules protected); the folder walked first, then each sub-folder met
$aclOf = {
  param($path)
  try {
    $sec = [System.IO.Directory]::GetAccessControl($path)
    $relDir = ''; if ($path.Length -ge $cut) { $relDir = $path.Substring($cut) }
    $entries = New-Object 'System.Collections.Generic.List[string]'
    foreach ($rule in $sec.GetAccessRules($true, $true, [System.Security.Principal.NTAccount])) {
      if ($entries.Count -ge 20) { break }
      $rights = [string]$rule.FileSystemRights
      $level = if ($rights -match 'FullControl') { 'F' } elseif ($rights -match 'Modify|Write') { 'W' } else { 'R' }
      if ([string]$rule.AccessControlType -eq 'Deny') { $level = '!' + $level }
      $inh = if ($rule.IsInherited) { '1' } else { '0' }
      $entries.Add("$($rule.IdentityReference.Value)|$level|$inh")
    }
    $dirAcls[$relDir] = [pscustomobject]@{ p = $relDir; x = [bool]$sec.AreAccessRulesProtected; e = $entries.ToArray() }
  } catch { }
}
if ($p.with_dirs) { & $aclOf $local }
$cold1 = @{ bytes = [long]0; files = 0 }; $cold3 = @{ bytes = [long]0; files = 0 }
$coldFiles = New-Object 'System.Collections.Generic.List[object]'
$junkStat = @{ bytes = [long]0; files = 0; examples = New-Object 'System.Collections.Generic.List[string]' }
$bySize = New-Object 'System.Collections.Generic.Dictionary[long,object]'
$big = New-Object 'System.Collections.Generic.List[object]'
$y1 = $now.AddDays(-365); $y3 = $now.AddDays(-1095)
$localCut = $local.TrimEnd('\').Length + 1
$onDir = { param($d) $t.folders++; if ($p.with_dirs) { & $aclOf $d.FullName }; if ($d.Parent.FullName.TrimEnd('\') -eq $local.TrimEnd('\')) { if (-not $top.ContainsKey($d.Name)) { $top[$d.Name] = @{ bytes = [long]0; files = 0 } } } }
$onFile = {
  param($f)
  $size = [long]$f.Length; $rel = $f.FullName.Substring($cut); $when = $f.LastWriteTimeUtc
  $t.bytes += $size; $t.files++
  # Every folder (5S scanner only, with_dirs): what is right in it; the scanner adds it up to the root
  if ($p.with_dirs) {
    $dk = [IO.Path]::GetDirectoryName($rel); if ($null -eq $dk) { $dk = '' }
    $ds = $dirStats[$dk]; if ($null -eq $ds) { $made = [DateTime]::MinValue; try { $made = $f.Directory.CreationTimeUtc } catch { }; $ds = @{ b = [long]0; f = 0; c1 = [long]0; c3 = [long]0; l = [DateTime]::MinValue; a = [DateTime]::MinValue; c = $made }; $dirStats[$dk] = $ds }
    $ds.b += $size; $ds.f++
    if ($when -lt $y1) { $ds.c1 += $size; if ($when -lt $y3) { $ds.c3 += $size } }
    if ($when -gt $ds.l) { $ds.l = $when }
    $seen = $f.LastAccessTimeUtc; if ($seen -gt $ds.a) { $ds.a = $seen }
  }
  $inside = $f.FullName.Substring($localCut); $slash = $inside.IndexOf('\')
  if ($slash -gt 0) { $first = $inside.Substring(0, $slash); if (-not $top.ContainsKey($first)) { $top[$first] = @{ bytes = [long]0; files = 0 } }; $top[$first].bytes += $size; $top[$first].files++ }
  $ext = $f.Extension.TrimStart('.').ToLowerInvariant(); if (-not $ext) { $ext = '—' } elseif ($ext.Length -gt 10) { $ext = $ext.Substring(0, 10) }
  if (-not $types.ContainsKey($ext)) { $types[$ext] = @{ files = 0; bytes = [long]0 } }; $types[$ext].files++; $types[$ext].bytes += $size
  if ($when -gt $state.last) { $state.last = $when }
  if ($when -lt $y1) {
    $cold1.bytes += $size; $cold1.files++
    if ($when -lt $y3) { $cold3.bytes += $size; $cold3.files++ }
    $coldFiles.Add([pscustomobject]@{ path = $rel; bytes = $size; modified = $when.ToString('yyyy-MM-ddTHH:mm:ssZ') })
    if ($coldFiles.Count -gt 400) { $keep = @($coldFiles | Sort-Object bytes -Descending | Select-Object -First 20); $coldFiles.Clear(); foreach ($k in $keep) { $coldFiles.Add($k) } }
  }
  if ($junk.IsMatch($f.Name)) { $junkStat.bytes += $size; $junkStat.files++; if ($junkStat.examples.Count -lt 5) { $junkStat.examples.Add($rel) } }
  if ($size -ge [long]$p.dup_min_bytes) {
    if ($bySize.ContainsKey($size)) { $bySize[$size].Add($f.FullName) } else { $l = New-Object 'System.Collections.Generic.List[string]'; $l.Add($f.FullName); $bySize[$size] = $l }
  }
  if ($size -ge [long]$p.fingerprint_min_bytes) {
    $big.Add([pscustomobject]@{ full = $f.FullName; path = $rel; size = $size; modified = $when.ToString('yyyy-MM-ddTHH:mm:ssZ') })
    if ($big.Count -gt (4 * [int]$p.fingerprints_max)) { $keep = @($big | Sort-Object size -Descending | Select-Object -First ([int]$p.fingerprints_max)); $big.Clear(); foreach ($k in $keep) { $big.Add($k) } }
  }
}
Walk $local $onFile $onDir
$walkMs = $watch.ElapsedMilliseconds
# Probable duplicates: same size first, then same fingerprint (biggest sizes first, within the budget)
$hashed = 0; $budgetHit = $false; $cache = @{}
# Fingerprints within a time budget too (hash_seconds, 0 = none): thousands of photos of the same size on a slow disk
# would otherwise hold the walk for many minutes; the duplicates are then marked truncated
$hashWatch = [Diagnostics.Stopwatch]::StartNew(); $hashSeconds = [int]$p.hash_seconds
# defer_hash (5S scanner): no fingerprint in the walk; the files to fingerprint are sent back (hash_todo) and a pass of
# their own computes them after the walk, within its budget, resumable
$hashMax = if ($p.defer_hash) { 0 } else { [int]$p.hash_files_max }
$groups = New-Object 'System.Collections.Generic.List[object]'
foreach ($size in @($bySize.Keys | Where-Object { $bySize[$_].Count -gt 1 } | Sort-Object -Descending)) {
  $byPrint = @{}
  foreach ($full in $bySize[$size]) {
    if ($hashed -ge $hashMax -or ($hashSeconds -gt 0 -and $hashWatch.Elapsed.TotalSeconds -gt $hashSeconds)) { $budgetHit = $true; break }
    try { $fp = Fingerprint $full $size; $hashed++; $cache[$full] = $fp } catch { continue }
    if (-not $byPrint.ContainsKey($fp)) { $byPrint[$fp] = New-Object 'System.Collections.Generic.List[string]' }
    $byPrint[$fp].Add($full.Substring($cut))
  }
  foreach ($fp in $byPrint.Keys) { if ($byPrint[$fp].Count -gt 1) { $n = [int]$byPrint[$fp].Count; $groups.Add([pscustomobject]@{ size = [long]$size; files = $n; wasted = [long]$size * ($n - 1); fingerprint = $fp; paths = @($byPrint[$fp] | Select-Object -First 5) }) } }
  if ($budgetHit) { break }
}
$wasted = [long]0; $dupFiles = 0
foreach ($g in $groups) { $wasted += [long]$g.wasted; $dupFiles += [int]$g.files }
# Fingerprints of the biggest files: the duplicates between folders
$prints = New-Object 'System.Collections.Generic.List[object]'
foreach ($b in @($big | Sort-Object size -Descending | Select-Object -First ([int]$p.fingerprints_max))) {
  $fp = $cache[$b.full]
  if (-not $fp) { if ($hashed -ge $hashMax -or ($hashSeconds -gt 0 -and $hashWatch.Elapsed.TotalSeconds -gt $hashSeconds)) { $budgetHit = $true; break }; try { $fp = Fingerprint $b.full $b.size; $hashed++ } catch { continue } }
  $prints.Add([pscustomobject]@{ path = $b.path; size = $b.size; fingerprint = $fp; modified = $b.modified })
}
$r = [ordered]@{}
$r.method = 'server'; $r.local_path = $local
$r.bytes = [long]$t.bytes; $r.files = [int]$t.files; $r.folders = [int]$t.folders; $r.truncated = $false; $r.denied_folders = [int]$state.denied
$r.top = @($top.GetEnumerator() | ForEach-Object { [pscustomobject]@{ name = [string]$_.Key; bytes = [long]$_.Value.bytes; files = [int]$_.Value.files } } | Sort-Object bytes -Descending | Select-Object -First 8)
$r.types = @($types.GetEnumerator() | ForEach-Object { [pscustomobject]@{ ext = [string]$_.Key; files = [int]$_.Value.files; bytes = [long]$_.Value.bytes } } | Sort-Object bytes -Descending | Select-Object -First 40)
$r.cold = @{ '1y' = @{ bytes = [long]$cold1.bytes; files = [int]$cold1.files }; '3y' = @{ bytes = [long]$cold3.bytes; files = [int]$cold3.files } }
$r.cold_top = @($coldFiles | Sort-Object bytes -Descending | Select-Object -First 5)
$r.junk = @{ bytes = [long]$junkStat.bytes; files = [int]$junkStat.files; examples = @($junkStat.examples) }
$r.last_modified = $null
if ($state.last -gt [DateTime]::MinValue) { $r.last_modified = $state.last.ToString('yyyy-MM-ddTHH:mm:ssZ') }
$r.duplicates = @{ groups = [int]$groups.Count; files = [int]$dupFiles; wasted_bytes = [long]$wasted; truncated = [bool]$budgetHit; hashed = [int]$hashed }
$r.duplicates.top = @($groups | Sort-Object wasted -Descending | Select-Object -First 200)
$r.fingerprints = @($prints | ForEach-Object { $_ })
if ($p.defer_hash) {
  # Same-size files (biggest sizes first, at most hash_files_max) and the biggest files: [path from the share, size]
  $same = New-Object 'System.Collections.Generic.List[object]'
  foreach ($size in @($bySize.Keys | Where-Object { $bySize[$_].Count -gt 1 } | Sort-Object -Descending)) {
    if ($same.Count -ge [int]$p.hash_files_max) { break }
    foreach ($full in $bySize[$size]) { $same.Add([pscustomobject]@{ p = $full.Substring($cut); s = [long]$size }) }
  }
  # Objects, not [path, size] pairs: ConvertTo-Json of PowerShell 5.1 turns nested arrays into {value, Count}
  $r.hash_todo = @{ same = @($same | ForEach-Object { $_ }); big = @($big | Sort-Object size -Descending | Select-Object -First ([int]$p.fingerprints_max) | ForEach-Object { [pscustomobject]@{ path = $_.path; size = [long]$_.size; modified = $_.modified } }) }
  $r.duplicates = @{ groups = 0; files = 0; wasted_bytes = [long]0; truncated = $true; hashed = 0; deferred = $true; top = @() }
}
if ($p.with_dirs) {
  $r.acls = @($dirAcls.Values | Select-Object -First 50000)
  $r.dirs = @($dirStats.GetEnumerator() | Select-Object -First 50000 | ForEach-Object {
    $l = $null; if ($_.Value.l -gt [DateTime]::MinValue) { $l = $_.Value.l.ToString('yyyy-MM-ddTHH:mm:ssZ') }
    $acc = $null; if ($_.Value.a -gt [DateTime]::MinValue) { $acc = $_.Value.a.ToString('yyyy-MM-ddTHH:mm:ssZ') }
    $cre = $null; if ($_.Value.c -gt [DateTime]::MinValue) { $cre = $_.Value.c.ToString('yyyy-MM-ddTHH:mm:ssZ') }
    [pscustomobject]@{ p = [string]$_.Key; b = [long]$_.Value.b; f = [int]$_.Value.f; c1 = [long]$_.Value.c1; c3 = [long]$_.Value.c3; l = $l; a = $acc; c = $cre } })
}
$r.walk_ms = [long]$walkMs; $r.elapsed_ms = [long]$watch.ElapsedMilliseconds
Send-Result $r
"""

_SENSITIVITY = _COMMON + r"""
$names = @($p.name_patterns | ForEach-Object { [regex]::new($_, 'IgnoreCase') })
$textExt = @{}; foreach ($e in $p.text_extensions) { $textExt[$e] = $true }
$textNames = @{}; foreach ($n in $p.text_names) { $textNames[$n] = $true }
$since = if ($p.since) { [DateTime]::Parse($p.since, $null, 'AdjustToUniversal, AssumeUniversal') } else { [DateTime]::MinValue }
$cursorPath = [string]$p.cursor_path
$hits = New-Object 'System.Collections.Generic.List[object]'
$cands = New-Object 'System.Collections.Generic.List[object]'
$max = [int]$p.candidates
$onDir = { param($d) }
$onFile = {
  param($f)
  $state.listed++
  $rel = $f.FullName.Substring($cut); $lower = $f.Name.ToLowerInvariant()
  foreach ($r in $names) { if ($r.IsMatch($lower)) { if ($hits.Count -lt 5000) { $hits.Add([pscustomobject]@{ path = $rel; size = [long]$f.Length }) }; break } }
  $ext = $f.Extension.TrimStart('.').ToLowerInvariant()
  if (($textExt.ContainsKey($ext) -or $textNames.ContainsKey($lower)) -and $f.Length -le [long]$p.max_file_bytes) {
    $when = $f.LastWriteTimeUtc
    if ($when -gt $since -or ($when -eq $since -and [string]::CompareOrdinal($rel, $cursorPath) -gt 0)) {
      $state.pending++
      $cands.Add([pscustomobject]@{ path = $rel; size = [long]$f.Length; ticks = $when.Ticks; modified = $when.ToString('yyyy-MM-ddTHH:mm:ss.ffffffZ') })
      if ($cands.Count -gt (4 * $max)) { $keep = @($cands | Sort-Object ticks, path | Select-Object -First $max); $cands.Clear(); foreach ($k in $keep) { $cands.Add($k) } }
    }
  }
}
Walk $local $onFile $onDir
$r = [ordered]@{}
$r.method = 'server'; $r.files_listed = [int]$state.listed; $r.denied_folders = [int]$state.denied
$r.name_hits = @($hits | ForEach-Object { $_ })
$r.candidates = @($cands | Sort-Object ticks, path | Select-Object -First $max | ForEach-Object { [pscustomobject]@{ path = $_.path; size = $_.size; modified = $_.modified } })
$r.pending_total = [int]$state.pending
$r.gone_paths = @($p.known_paths | Where-Object { $_ -and -not (Test-Path -LiteralPath (Join-Path $base $_)) })
$r.elapsed_ms = [long]$watch.ElapsedMilliseconds
Send-Result $r
"""


def _script(template: str, params: dict[str, Any]) -> str:
    return template.replace("__PARAMS__", json.dumps(params, ensure_ascii=True))


def _parse(output: str) -> dict[str, Any]:
    lines = [line for line in str(output or "").splitlines() if line.strip().startswith("{")]
    if not lines:
        return {}
    try:
        value = json.loads(lines[-1])
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


class ServerScanError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _run(template: str, params: dict[str, Any], *, connection: dict[str, Any], timeout: int) -> dict[str, Any]:
    answer = run_powershell(script=_script(template, params), timeout=timeout, **connection)
    result = _parse(answer["output"])
    if not result:
        raise ServerScanError("SCAN_NO_ANSWER", str((answer.get("errors") or ["The server gave no answer"])[0])[:400])
    if result.get("error"):
        raise ServerScanError(str(result["error"]), str(result.get("message") or result["error"])[:400])
    return result


def measure(*, share: str, path: str, connection: dict[str, Any], junk_pattern: str, timeout: int = 3600,
            dup_min_bytes: int = 64 * 1024, fingerprint_min_bytes: int = 1024 * 1024, fingerprints_max: int = 500,
            hash_files_max: int = 20000) -> dict[str, Any]:
    return _run(_MEASURE, {"share": share, "path": path, "junk_pattern": junk_pattern, "dup_min_bytes": dup_min_bytes,
                           "fingerprint_min_bytes": fingerprint_min_bytes, "fingerprints_max": fingerprints_max,
                           "hash_files_max": hash_files_max}, connection=connection, timeout=timeout)


def sensitivity_listing(*, share: str, path: str, connection: dict[str, Any], name_patterns: list[str], text_extensions: list[str],
                        text_names: list[str], max_file_bytes: int, since: str | None, cursor_path: str | None,
                        known_paths: list[str], candidates: int, timeout: int = 3600) -> dict[str, Any]:
    return _run(_SENSITIVITY, {"share": share, "path": path, "name_patterns": name_patterns, "text_extensions": text_extensions,
                               "text_names": text_names, "max_file_bytes": max_file_bytes, "since": since, "cursor_path": cursor_path or "",
                               "known_paths": known_paths[:200], "candidates": candidates}, connection=connection, timeout=timeout)
