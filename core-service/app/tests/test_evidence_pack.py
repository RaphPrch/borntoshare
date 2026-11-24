from __future__ import annotations

import hashlib
import io
import zipfile
from datetime import date

from app.services import evidence_pack


def test_a_csv_cell_never_runs_as_a_formula():
    data, count = evidence_pack._csv(["a", "b"], [["=cmd()", "ok"], [None, "-1"]])
    text = data.decode("utf-8-sig")
    assert count == 2
    assert "'=cmd()" in text and "'-1" in text


def test_the_pack_holds_its_files_and_their_checksums(monkeypatch):
    monkeypatch.setattr(evidence_pack, "_folder_ids", lambda db, **k: [4])
    monkeypatch.setattr(evidence_pack, "_events", lambda since, until, **k: evidence_pack._csv(["action"], [["access_request.approve"]]))
    monkeypatch.setattr(evidence_pack, "_requests", lambda db, s, u, f: evidence_pack._csv(["request"], [["AR-1"], ["AR-2"]]))
    monkeypatch.setattr(evidence_pack, "_reviews", lambda db, s, u, f: evidence_pack._csv(["review"], []))
    monkeypatch.setattr(evidence_pack, "_access_today", lambda db, root: evidence_pack._csv(["login"], [["jdupont"]]))
    data, name = evidence_pack.build(None, since=date(2026, 1, 1), until=date(2026, 3, 31), root_id=4, by="Admin")
    assert name == "b2s-evidence-root4-2026-01-01-2026-03-31.zip"
    archive = zipfile.ZipFile(io.BytesIO(data))
    assert sorted(archive.namelist()) == ["MANIFEST.txt", "access_requests.csv", "access_reviews.csv", "access_today.csv", "audit_events.csv"]
    manifest = archive.read("MANIFEST.txt").decode("utf-8")
    assert "dossier 4" in manifest and "Par : Admin" in manifest
    # Each file is listed with its row count and the SHA-256 of its content
    assert f"access_requests.csv · 2 · {hashlib.sha256(archive.read('access_requests.csv')).hexdigest()}" in manifest
