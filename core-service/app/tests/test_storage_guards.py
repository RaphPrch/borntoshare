from __future__ import annotations

from app.services.storage_guards import normalize_root_path, rewrite_unc_host, same_host, unc_host


def test_unc_host() -> None:
    assert unc_host(r"\\fs12\ops\archive") == "fs12"
    assert unc_host("//fs12.example.org/ops") == "fs12.example.org"
    assert unc_host("/srv/share") is None


def test_same_host_accepts_short_name_and_fqdn_only() -> None:
    assert same_host("fs12", "fs12.example.org")
    assert same_host("FS12.example.org", "fs12.example.org.")
    assert not same_host("fs12.example.org", "fs12.other.org")
    assert not same_host("fs12", "fs13.example.org")
    assert not same_host("10.0.0.1", "10.0.0.2")
    assert not same_host("", "fs12")


def test_rewrite_keeps_the_share_and_folder() -> None:
    assert rewrite_unc_host(r"\\fs12\ops\archive", "fs40.example.org") == r"\\fs40.example.org\ops\archive"
    assert rewrite_unc_host(r"\\fs12", "fs40") == r"\\fs40"
    assert normalize_root_path(r"\\FS40\Ops\Archive\\") == "/fs40/ops/archive"
