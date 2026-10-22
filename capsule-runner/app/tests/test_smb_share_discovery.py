from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.actions import smb


def test_only_data_shares_are_offered(monkeypatch) -> None:
    listing = "\n".join([
        "Disk|corp|",
        "Disk|SYSVOL|",
        "Disk|netlogon|Logon server share",
        "Disk|C$|Default share",
        "Disk|ADMIN$|Remote Admin",
        "IPC|IPC$|IPC Service",
        "Disk|projects|",
        "Disk|corp|",
    ]).encode()
    monkeypatch.setattr(smb, "run_samba", lambda *a, **kw: SimpleNamespace(stdout=listing, stderr=b""))

    shares = smb._discover_smb_shares(host="dc01", port=445, username="u", password="p", timeout=5)

    assert shares == ["\\\\dc01\\corp", "\\\\dc01\\projects"]
