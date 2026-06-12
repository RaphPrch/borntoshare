from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.actions import kerberos


def test_kerberos_uses_per_job_temp_cache(monkeypatch) -> None:
    captured = {"env": None}

    class _Proc:
        stdout = b""
        stderr = b""

    def _fake_run(cmd, input=None, capture_output=None, timeout=None, check=None, env=None):
        captured["env"] = dict(env or {})
        return _Proc()

    monkeypatch.setattr(kerberos.subprocess, "run", _fake_run)
    ok, msg, details = kerberos.test_kerberos(
        {
            "job_id": 77,
            "principal": "svc",
            "realm": "EXAMPLE.LOCAL",
            "password": "secret",
            "timeout": 1,
        }
    )

    assert ok is True
    assert "KRB5CCNAME" in (captured["env"] or {})
    assert "krb5cc_77_" in captured["env"]["KRB5CCNAME"]

