from __future__ import annotations

from app.services.naming_policy import (
    compute_rootcode,
    enforce_sam_length,
    normalize_rootcode_strategy,
    resolve_group_name_from_effective_policy,
    serialize_rootcode_strategy_for_storage,
)


def test_compute_rootcode_path_last2() -> None:
    out = compute_rootcode(
        "\\\\files\\corp\\finance\\p1",
        strategy="BASENAME",
        replace_map={"\\": "_", "/": "_", " ": "_", "-": "_"},
        uppercase=True,
    )
    assert out == "P1"


def test_compute_rootcode_basename() -> None:
    out = compute_rootcode(
        "\\\\files\\corp\\finance\\p1",
        strategy="BASENAME",
        replace_map={"\\": "_", "/": "_", " ": "_", "-": "_"},
        uppercase=True,
    )
    assert out == "P1"


def test_compute_rootcode_path_all() -> None:
    out = compute_rootcode(
        "\\\\files\\corp\\finance\\p1",
        strategy="PATH_ALL",
        replace_map={"\\": "_", "/": "_", " ": "_", "-": "_"},
        uppercase=True,
    )
    assert out == "CORP_FINANCE_P1"


def test_enforce_sam_length_uses_stable_hash_suffix() -> None:
    raw = "A" * 80
    out = enforce_sam_length(raw, max_len=64, uppercase=True)
    assert len(out) == 64
    assert out[57] == "_"
    assert len(out.split("_")[-1]) == 6


def test_group_resolution_with_zone_prefix_template() -> None:
    policy = {
        "group_prefix": "B2S",
        "template": "{PREFIX}_{ROOTCODE}_{PERM}",
        "normalize_uppercase": True,
        "max_sam_length": 64,
        "replace_map_json": '{"\\\\":"_","/":"_"," ":"_","-":"_"}',
        "rootcode_strategy": "BASENAME",
    }
    out = resolve_group_name_from_effective_policy(
        effective_policy=policy,
        zone_code="CS",
        storage_root_path="\\\\files\\corp\\finance\\p1",
        perm="read",
    )
    assert out["samAccountName"] == "B2S_P1_RX"
    assert out["cn"] == "B2S_P1_RX"


def test_group_resolution_appends_suffix_when_template_has_no_suffix_slot() -> None:
    policy = {
        "group_prefix": "B2S",
        "template": "{PREFIX}_{ROOTCODE}_{PERM}",
        "normalize_uppercase": True,
        "max_sam_length": 64,
        "replace_map_json": '{"\\\\":"_","/":"_"," ":"_","-":"_"}',
        "rootcode_strategy": "BASENAME",
    }
    out = resolve_group_name_from_effective_policy(
        effective_policy=policy,
        zone_code="CS",
        storage_root_path="\\\\files\\corp\\finance\\p1",
        perm="read",
        suffix="TEAM1",
    )
    assert out["samAccountName"] == "B2S_P1_RX_TEAM1"


def test_group_resolution_does_not_duplicate_profile_when_same_as_perm() -> None:
    policy = {
        "group_prefix": "B2S",
        "template": "{PREFIX}_{ROOTCODE}_{PERM}",
        "normalize_uppercase": True,
        "max_sam_length": 64,
        "replace_map_json": '{"\\\\":"_","/":"_"," ":"_","-":"_"}',
        "rootcode_strategy": "BASENAME",
    }
    out = resolve_group_name_from_effective_policy(
        effective_policy=policy,
        zone_code="CS",
        storage_root_path="\\\\files\\corp\\finance\\p1",
        perm="write",
        profile="write",
    )
    assert out["samAccountName"] == "B2S_P1_RW"


def test_group_resolution_does_not_duplicate_suffix_when_same_as_perm() -> None:
    policy = {
        "group_prefix": "B2S",
        "template": "{PREFIX}_{ROOTCODE}_{PERM}",
        "normalize_uppercase": True,
        "max_sam_length": 64,
        "replace_map_json": '{"\\\\":"_","/":"_"," ":"_","-":"_"}',
        "rootcode_strategy": "BASENAME",
    }
    out = resolve_group_name_from_effective_policy(
        effective_policy=policy,
        zone_code="CS",
        storage_root_path="\\\\files\\corp\\finance\\p1",
        perm="write",
        suffix="write",
    )
    assert out["samAccountName"] == "B2S_P1_RW"


def test_rootcode_strategy_normalization_and_storage_serialization() -> None:
    assert normalize_rootcode_strategy("BASENAME") == "BASENAME"
    assert normalize_rootcode_strategy("PATH_ALL") == "PATH_ALL"
    assert normalize_rootcode_strategy("unknown") == "BASENAME"
    assert serialize_rootcode_strategy_for_storage("BASENAME") == "BASENAME"
    assert serialize_rootcode_strategy_for_storage("unknown") == "BASENAME"
    assert serialize_rootcode_strategy_for_storage("PATH_ALL") == "PATH_ALL"
