from __future__ import annotations


def naming_perm(level: str) -> str:
    lv = str(level or "").strip().upper()
    if lv in {"WRITE", "RW", "W", "MODIFY", "CHANGE", "CONTRIBUTION"}:
        return "RW"
    return "RX"
