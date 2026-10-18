from __future__ import annotations

from dataclasses import dataclass


QUEUE_IDENTITY = "capsule_identity"
QUEUE_PROVISIONING = "capsule_provisioning"
QUEUE_ACL = "capsule_acl"
QUEUE_PROBES = "capsule_probes"


@dataclass(frozen=True)
class JobContract:
    job_type: str
    default_action: str
    queue_name: str
    actor_name: str


JOB_CONTRACTS: dict[str, JobContract] = {
    "DIRECTORY_SNAPSHOT": JobContract(
        job_type="DIRECTORY_SNAPSHOT",
        default_action="collect_directory_snapshot",
        queue_name=QUEUE_IDENTITY,
        actor_name="run_identity_job",
    ),
    "IDENTITY_DISCOVERY": JobContract(
        job_type="IDENTITY_DISCOVERY",
        default_action="search_ldap_principals",
        queue_name=QUEUE_IDENTITY,
        actor_name="run_identity_job",
    ),
    "IDENTITY_SEARCH": JobContract(
        job_type="IDENTITY_SEARCH",
        default_action="search_ldap_principals",
        queue_name=QUEUE_IDENTITY,
        actor_name="run_identity_job",
    ),
    "LDAP_TEST": JobContract(
        job_type="LDAP_TEST",
        default_action="test_ldap",
        queue_name=QUEUE_IDENTITY,
        actor_name="run_identity_job",
    ),
    "AD_GROUP_ENSURE": JobContract(
        job_type="AD_GROUP_ENSURE",
        default_action="ensure_ad_group",
        queue_name=QUEUE_PROVISIONING,
        actor_name="run_provisioning_job",
    ),
    "AD_GROUP_MEMBERSHIP": JobContract(
        job_type="AD_GROUP_MEMBERSHIP",
        default_action="ensure_ad_group_member",
        queue_name=QUEUE_PROVISIONING,
        actor_name="run_provisioning_job",
    ),
    "AD_GROUP_MEMBERSHIP_REMOVE": JobContract(
        job_type="AD_GROUP_MEMBERSHIP_REMOVE",
        default_action="remove_ad_group_member",
        queue_name=QUEUE_PROVISIONING,
        actor_name="run_provisioning_job",
    ),
    "GROUP_USERS_DISCOVERY": JobContract(
        job_type="GROUP_USERS_DISCOVERY",
        default_action="discover_group_users_recursive",
        queue_name=QUEUE_PROVISIONING,
        actor_name="run_provisioning_job",
    ),
    "ACL_APPLY": JobContract(
        job_type="ACL_APPLY",
        default_action="acl_apply_via_group",
        queue_name=QUEUE_ACL,
        actor_name="run_acl_job",
    ),
    "SMB_PROBE": JobContract(
        job_type="SMB_PROBE",
        default_action="test_smb_ntlm",
        queue_name=QUEUE_PROBES,
        actor_name="run_probe_job",
    ),
}


def normalize_job_type(job_type: str | None) -> str:
    return str(job_type or "").strip().upper()


def contract_for_job_type(job_type: str | None) -> JobContract:
    normalized = normalize_job_type(job_type)
    try:
        return JOB_CONTRACTS[normalized]
    except KeyError as exc:
        raise ValueError(f"Unsupported job_type: {normalized or '<empty>'}") from exc


def default_action_for_job_type(job_type: str | None) -> str:
    return contract_for_job_type(job_type).default_action


def queue_for_job_type(job_type: str | None) -> str:
    return contract_for_job_type(job_type).queue_name


def actor_for_job_type(job_type: str | None) -> str:
    return contract_for_job_type(job_type).actor_name


def queue_job_types_csv() -> str:
    return ",".join(sorted(JOB_CONTRACTS))
