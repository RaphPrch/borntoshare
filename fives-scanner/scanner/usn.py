"""The NTFS change journal (USN) of a volume, read ON the file server (C# compiled by PowerShell, no agent).

query:    the journal of the volume (its id, its first and next USN);
changed:  the folders where something changed since a USN: the parent folder of every record, resolved to its path
          (OpenFileById + GetFinalPathNameByHandle). Locale independent (no fsutil text to parse).
A folder scanned again only where its first-level sub-folders changed: minutes instead of hours on big shares.
"""
from __future__ import annotations

CSHARP = r'''
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;
using Microsoft.Win32.SafeHandles;

public static class B2sUsn {
  [StructLayout(LayoutKind.Sequential)]
  struct USN_JOURNAL_DATA_V0 { public ulong UsnJournalID; public long FirstUsn; public long NextUsn; public long LowestValidUsn; public long MaxUsn; public ulong MaximumSize; public ulong AllocationDelta; }
  [StructLayout(LayoutKind.Sequential)]
  struct READ_USN_JOURNAL_DATA_V0 { public long StartUsn; public uint ReasonMask; public uint ReturnOnlyOnClose; public ulong Timeout; public ulong BytesToWaitFor; public ulong UsnJournalID; }
  [StructLayout(LayoutKind.Sequential)]
  struct FILE_ID_DESCRIPTOR { public int dwSize; public int Type; public long FileId; public long Pad; }
  const uint FSCTL_QUERY_USN_JOURNAL = 0x000900f4;
  const uint FSCTL_READ_USN_JOURNAL = 0x000900bb;
  [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
  static extern SafeFileHandle CreateFile(string name, uint access, uint share, IntPtr sa, uint disposition, uint flags, IntPtr template);
  [DllImport("kernel32.dll", SetLastError = true)]
  static extern bool DeviceIoControl(SafeFileHandle h, uint code, IntPtr inBuf, int inSize, out USN_JOURNAL_DATA_V0 outBuf, int outSize, out int returned, IntPtr ov);
  [DllImport("kernel32.dll", SetLastError = true)]
  static extern bool DeviceIoControl(SafeFileHandle h, uint code, ref READ_USN_JOURNAL_DATA_V0 inBuf, int inSize, IntPtr outBuf, int outSize, out int returned, IntPtr ov);
  [DllImport("kernel32.dll", SetLastError = true)]
  static extern SafeFileHandle OpenFileById(SafeFileHandle hint, ref FILE_ID_DESCRIPTOR id, uint access, uint share, IntPtr sa, uint flags);
  [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
  static extern uint GetFinalPathNameByHandle(SafeFileHandle h, StringBuilder path, uint size, uint flags);

  static SafeFileHandle Volume(string drive) {
    var h = CreateFile(@"\\.\" + drive.TrimEnd('\\'), 0x80000000, 3, IntPtr.Zero, 3, 0, IntPtr.Zero);
    if (h.IsInvalid) throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
    return h;
  }

  public static long[] Query(string drive) {
    using (var v = Volume(drive)) {
      USN_JOURNAL_DATA_V0 data; int returned;
      if (!DeviceIoControl(v, FSCTL_QUERY_USN_JOURNAL, IntPtr.Zero, 0, out data, Marshal.SizeOf(typeof(USN_JOURNAL_DATA_V0)), out returned, IntPtr.Zero))
        throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
      return new long[] { unchecked((long)data.UsnJournalID), data.FirstUsn, data.NextUsn };
    }
  }

  // Paths of the folders holding a change since startUsn (stops at untilUsn); null when there are too many
  public static string[] ChangedFolders(string drive, long journalId, long startUsn, long untilUsn, int maxFolders) {
    var parents = new HashSet<long>();
    using (var v = Volume(drive)) {
      var request = new READ_USN_JOURNAL_DATA_V0 { StartUsn = startUsn, ReasonMask = 0xFFFFFFFF, UsnJournalID = unchecked((ulong)journalId) };
      int size = 1 << 16; IntPtr buffer = Marshal.AllocHGlobal(size);
      try {
        while (request.StartUsn < untilUsn) {
          int returned;
          if (!DeviceIoControl(v, FSCTL_READ_USN_JOURNAL, ref request, Marshal.SizeOf(typeof(READ_USN_JOURNAL_DATA_V0)), buffer, size, out returned, IntPtr.Zero))
            throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
          long next = Marshal.ReadInt64(buffer);
          if (returned <= 8 || next == request.StartUsn) break;
          int offset = 8;
          while (offset < returned) {
            int length = Marshal.ReadInt32(buffer, offset);
            if (length <= 0) break;
            short major = Marshal.ReadInt16(buffer, offset + 4);
            if (major == 2) parents.Add(Marshal.ReadInt64(buffer, offset + 16));
            offset += length;
          }
          if (parents.Count > maxFolders) return null;
          request.StartUsn = next;
        }
      } finally { Marshal.FreeHGlobal(buffer); }
      var paths = new List<string>();
      foreach (var frn in parents) {
        var id = new FILE_ID_DESCRIPTOR { dwSize = 24, Type = 0, FileId = frn };
        using (var h = OpenFileById(v, ref id, 0x80, 7, IntPtr.Zero, 0x02000000)) {
          if (h.IsInvalid) continue;  // folder deleted since: its parent changed too
          var sb = new StringBuilder(1024);
          uint n = GetFinalPathNameByHandle(h, sb, 1024, 0);
          if (n > 0 && n < 1024) paths.Add(sb.ToString().Replace(@"\\?\", ""));
        }
      }
      return paths.ToArray();
    }
  }
}
'''

# Inside a script that already has $p (volume, under, since_usn, journal_id, max_folders): sets $journal
FRAGMENT = r"""
$journal = $null
try {
  if (-not ('B2sUsn' -as [type])) { Add-Type -TypeDefinition @'
__CSHARP__
'@ }
  $q = [B2sUsn]::Query($p.volume)
  $journal = [ordered]@{ journal_id = ('{0:x16}' -f $q[0]); first_usn = $q[1]; next_usn = $q[2]; changed = $null; complete = $false }
  if ($p.since_usn -ne $null -and $p.journal_id -eq $journal.journal_id -and [long]$p.since_usn -ge $q[1]) {
    $folders = [B2sUsn]::ChangedFolders($p.volume, $q[0], [long]$p.since_usn, $q[2], [int]$p.max_folders)
    if ($folders -ne $null) { $journal.changed = @($folders | Where-Object { $_.StartsWith($p.under, [StringComparison]::OrdinalIgnoreCase) }); $journal.complete = $true }
  }
} catch { $journal = [ordered]@{ error = 'USN_FAILED'; message = "$($_.Exception.Message)" } }
"""


def fragment() -> str:
    return FRAGMENT.replace("__CSHARP__", CSHARP)
