"""Smart policies: « if the folders match this condition, then do this ».

The condition is an express search of the folders (app/services/folder_query.py). Each run compares the folders
that match with those that matched before (governance_policy_hits):
- a folder that starts matching gets the actions once: tag added, guardians told;
- while it matches, the alert of the policy stays open (and reopens if someone marks it resolved);
- a folder that stops matching loses its hit and its alert is resolved. The tag stays (removing it is a human choice),
  unless the policy says « remove_tag »: then it goes with the condition (automatic tags).
- tasks (ACL read and content, sensitivity scan) go to the workers for the folders that match, at most once per
  frequency per folder and MAX_JOBS_PER_RUN folders per run: the next runs take the rest.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.services import folder_query

logger = logging.getLogger("core.policies")
SEVERITIES = ("info", "warning", "high", "critical")
JOB_KINDS = ("check", "measure", "sensitivity")
MAX_JOBS_PER_RUN = 50


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _load(value: Any, default: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value) if value else default
    except (TypeError, ValueError):
        return default


def list_policies(db: Session) -> list[dict[str, Any]]:
    rows = db.execute(text("SELECT * FROM governance_policies ORDER BY name")).mappings().all()
    return [_row(row) for row in rows]


def get_policy(db: Session, policy_id: int) -> dict[str, Any] | None:
    row = db.execute(text("SELECT * FROM governance_policies WHERE id = :id"), {"id": int(policy_id)}).mappings().first()
    return _row(row) if row else None


def _row(row: Any) -> dict[str, Any]:
    iso = lambda value: value.isoformat() + "Z" if value else None  # noqa: E731
    return {
        "id": int(row["id"]),
        "name": row["name"],
        "description": row["description"],
        "enabled": bool(row["enabled"]),
        "condition": row["condition_query"],
        "actions": _load(row["actions_json"], {}),
        "last_run_at": iso(row["last_run_at"]),
        "last_matched": row["last_matched"],
        "last_new": row["last_new"],
        "last_error": row["last_error"],
        "updated_by": row["updated_by"],
        "updated_at": iso(row["updated_at"]),
    }


def folder_rows(db: Session) -> list[dict[str, Any]]:
    """Every governed folder with what the conditions look at (tags, guardians, alerts, size, sensitivity…)."""
    from app.data.repositories.storage_roots_views_repo import StorageRootsViewsRepo
    from app.services.dfs_links import dfs_paths_and_replicas

    rows = StorageRootsViewsRepo(db).list_context()
    try:
        dfs_paths, _replicas = dfs_paths_and_replicas(db)
    except Exception:
        dfs_paths = {}
    return [{**row, "dfs_path": dfs_paths.get(int(row.get("storage_root_id") or 0))} for row in rows]


def matching(rows: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    return [row for row in rows if folder_query.matches(row, query)]


def _guardian_emails(db: Session, root_ids: list[int]) -> dict[int, list[str]]:
    if not root_ids:
        return {}
    rows = db.execute(
        text(
            """
            SELECT r.root_id, i.email FROM storage_root_roles r JOIN identities i ON i.id = r.identity_id
            WHERE LOWER(r.role) = 'guardian' AND i.email IS NOT NULL AND r.root_id IN :ids
            """
        ).bindparams(bindparam("ids", expanding=True)),
        {"ids": root_ids},
    ).all()
    out: dict[int, list[str]] = {}
    for root_id, email in rows:
        out.setdefault(int(root_id), []).append(str(email))
    return out


def _alert_key(policy_id: int, root_id: int) -> str:
    return f"policy:{int(policy_id)}:storage_root:{int(root_id)}"


def _raise_alert(db: Session, policy: dict[str, Any], row: dict[str, Any], severity: str) -> None:
    from app.data.repositories.governance_alerts_repo import GovernanceAlertsRepo

    root_id = int(row["storage_root_id"])
    GovernanceAlertsRepo(db)._upsert_alert(
        {
            "alert_key": _alert_key(policy["id"], root_id),
            "scope_type": "storage_root",
            "scope_id": root_id,
            "alert_type": f"policy:{policy['id']}",
            "severity": severity if severity in SEVERITIES else "warning",
            "title": policy["name"],
            "message": policy.get("description") or f"Le dossier correspond à la politique « {policy['name']} » ({policy['condition']})",
            "source_type": "policy",
            "source_id": str(policy["id"]),
            "zone_id": row.get("zone_id"),
            "storage_endpoint_id": row.get("storage_endpoint_id"),
            "storage_root_id": root_id,
            "metadata_json": {"policy_id": policy["id"], "condition": policy["condition"], "storage_root_name": row.get("storage_root_name")},
        }
    )


def _resolve_alerts(db: Session, policy_id: int, root_ids: list[int] | None = None) -> int:
    """The alerts of a policy on folders that no longer match it (all of them when root_ids is None)."""
    from app.services.extensions import dispatch, event_from_resolved_alert

    query = "SELECT alert_key, alert_type, severity, title, message FROM governance_alerts WHERE alert_type = :type AND status <> 'resolved'"
    params: dict[str, Any] = {"type": f"policy:{int(policy_id)}"}
    rows = [dict(row) for row in db.execute(text(query), params).mappings().all()]
    if root_ids is not None:
        keys = {_alert_key(policy_id, root_id) for root_id in root_ids}
        rows = [row for row in rows if row["alert_key"] in keys]
    if not rows:
        return 0
    db.execute(
        text("UPDATE governance_alerts SET status = 'resolved', resolved_at = :now WHERE alert_key IN :keys AND status <> 'resolved'")
        .bindparams(bindparam("keys", expanding=True)),
        {"now": _now(), "keys": [row["alert_key"] for row in rows]},
    )
    for row in rows:
        dispatch(event_from_resolved_alert(row))
    return len(rows)


def _add_tag(db: Session, root_id: int, tag_id: int) -> bool:
    """True when the tag was added (False: already there)."""
    params = {"root": int(root_id), "tag": int(tag_id)}
    if db.execute(text("SELECT 1 FROM storage_root_tags WHERE storage_root_id = :root AND tag_id = :tag"), params).first():
        return False
    db.execute(text("INSERT IGNORE INTO storage_root_tags (storage_root_id, tag_id) VALUES (:root, :tag)"), params)
    return True


def _notify(db: Session, policy: dict[str, Any], rows: list[dict[str, Any]]) -> int:
    from app.services import notifications

    config = notifications.settings(db)
    if not config.get("enabled"):
        return 0
    emails = _guardian_emails(db, [int(row["storage_root_id"]) for row in rows])
    sent = 0
    for row in rows:
        root_id = int(row["storage_root_id"])
        recipients = emails.get(root_id) or []
        if not recipients:
            continue
        name = row.get("storage_root_name") or row.get("root_path")
        from app.services import mail_templates as mt

        url = notifications._url(config, f"/storage-roots?selected={root_id}")
        html = mt.layout(
            preheader=f"{name} correspond à la politique « {policy['name']} »", eyebrow="Politique", title=f"{policy['name']} : {name}",
            intro=policy.get("description") or f"Le dossier {name} correspond à la politique « {policy['name']} ».",
            blocks=[mt.details([("Dossier", f"<strong>{mt.e(name)}</strong><br>{mt.code(row.get('root_path') or '')}"),
                                ("Condition", mt.code(policy["condition"]))])],
            buttons=[mt.button("Voir le dossier", url)] if url else [],
            footer=f"Vous recevez ce mail parce que vous êtes gardien du dossier {name}.",
        )
        notifications.queue(
            f"policy:{policy['id']}:root:{root_id}:{_now():%Y%m%d%H%M}",
            recipients,
            f"[BornToShare] {policy['name']} : {name}",
            f"Le dossier {name} ({row.get('root_path')}) correspond à la politique « {policy['name']} ».\n"
            + (f"\n{policy['description']}\n" if policy.get("description") else "")
            + f"\nCondition : {policy['condition']}"
            + notifications._link(config, f"/storage-roots?selected={root_id}"),
            html,
        )
        sent += 1
    return sent


def _due_jobs(db: Session, policy_id: int, root_ids: list[int], spec: dict[str, Any], now: datetime) -> list[dict[str, Any]]:
    """The tasks due on the matching folders: never got them, or longer ago than the frequency."""
    kinds = [kind for kind in spec.get("kinds") or [] if kind in JOB_KINDS]
    if not kinds or not root_ids:
        return []
    hours = max(1, int(spec.get("every_hours") or 24))
    rows = db.execute(
        text(
            """
            SELECT storage_root_id FROM governance_policy_hits
            WHERE policy_id = :id AND storage_root_id IN :ids
              AND (last_job_at IS NULL OR last_job_at < :now - INTERVAL :hours HOUR)
            ORDER BY last_job_at IS NOT NULL, last_job_at, storage_root_id
            LIMIT :cap
            """
        ).bindparams(bindparam("ids", expanding=True)),
        {"id": int(policy_id), "ids": root_ids, "now": now, "hours": hours, "cap": MAX_JOBS_PER_RUN},
    ).all()
    due = [int(root_id) for (root_id,) in rows]
    # The date is recorded by dispatch_jobs once the task is really in the queue: a refused one is tried again next run
    return [{"policy_id": int(policy_id), "storage_root_id": root_id, "kind": kind} for root_id in due for kind in kinds]


async def dispatch_jobs(db: Session, jobs: list[dict[str, Any]]) -> dict[str, int]:
    """Hand the tasks of a run to the workers (job queue); a folder whose tasks all went in gets its date."""
    from app.services import sensitivity
    from app.services.probe_service import submit_probe_run

    from app.services import scans

    done = {"check": 0, "measure": 0, "sensitivity": 0, "failed": 0}
    failed: set[tuple[int, int]] = set()
    for job in jobs:
        root_id = int(job["storage_root_id"])
        key = (int(job.get("policy_id") or 0), root_id)
        try:
            # Same request as the check of a folder, but errors are not swallowed here
            if job["kind"] == "measure":
                # The scanner of the 5S module when it is on, the worker of the core otherwise
                await scans.request_measure(db, root_id, reason="policy", by="Politique")
            else:
                protocol = "smb" if job["kind"] == "check" else "sensitivity"
                queued = await submit_probe_run({
                    "kind": "storage-root", "protocol": protocol, "scope": "read",
                    "target": {"storage_root_id": root_id},
                    "options": {"timeout_sec": 30 if protocol == "smb" else 600},
                    "context": {"storage_root_id": root_id, "ui_origin": "policy"},
                })
                if job["kind"] == "sensitivity":
                    sensitivity.mark_requested(db, root_id, int(queued.get("job_id") or 0) or None)
            done[job["kind"]] += 1
        except Exception:
            logger.warning("POLICY_JOB_NOT_QUEUED", extra={"storage_root_id": root_id, "kind": job["kind"]}, exc_info=True)
            done["failed"] += 1
            failed.add(key)
    given = sorted({(int(job.get("policy_id") or 0), int(job["storage_root_id"])) for job in jobs} - failed)
    if given:
        db.execute(
            text("UPDATE governance_policy_hits SET last_job_at = :now WHERE policy_id = :policy AND storage_root_id = :root"),
            [{"now": _now(), "policy": policy_id, "root": root_id} for policy_id, root_id in given],
        )
        db.commit()
    return done


def run_policy(db: Session, policy: dict[str, Any], rows: list[dict[str, Any]], *, only_root_ids: set[int] | None = None,
               allow_jobs: bool = True) -> dict[str, Any]:
    """Evaluate one policy; only_root_ids limits the run to some folders (after a scan of one folder)."""
    pid = int(policy["id"])
    scope = [row for row in rows if only_root_ids is None or int(row.get("storage_root_id") or 0) in only_root_ids]
    matched = {int(row["storage_root_id"]): row for row in matching(scope, policy["condition"])}
    hits_query = "SELECT storage_root_id FROM governance_policy_hits WHERE policy_id = :id"
    before = {int(value) for (value,) in db.execute(text(hits_query), {"id": pid}).all()}
    if only_root_ids is not None:
        before &= only_root_ids
    new_ids = sorted(set(matched) - before)
    gone_ids = sorted(before - set(matched))
    actions = policy.get("actions") or {}
    now = _now()

    if matched:
        db.execute(
            text(
                """
                INSERT INTO governance_policy_hits (policy_id, storage_root_id, first_matched_at, last_matched_at)
                VALUES (:policy, :root, :now, :now)
                ON DUPLICATE KEY UPDATE last_matched_at = VALUES(last_matched_at)
                """
            ),
            [{"policy": pid, "root": root_id, "now": now} for root_id in matched],
        )
    if gone_ids:
        db.execute(
            text("DELETE FROM governance_policy_hits WHERE policy_id = :id AND storage_root_id IN :ids").bindparams(bindparam("ids", expanding=True)),
            {"id": pid, "ids": gone_ids},
        )
    tagged = 0
    untagged = 0
    if actions.get("add_tag"):
        tagged = sum(1 for root_id in new_ids if _add_tag(db, root_id, int(actions["add_tag"])))
        if actions.get("remove_tag") and gone_ids:
            untagged = db.execute(
                text("DELETE FROM storage_root_tags WHERE tag_id = :tag AND storage_root_id IN :ids").bindparams(bindparam("ids", expanding=True)),
                {"tag": int(actions["add_tag"]), "ids": gone_ids},
            ).rowcount or 0
    # The tag on the sub-folders too (their name, the files found in them); gone with the option
    sub_added = sub_removed = 0
    if actions.get("add_tag"):
        from app.services import folder_tags

        if actions.get("subfolders") and folder_tags.supported(policy["condition"]):
            for row in scope:
                paths = folder_tags.matching_folders(db, row, policy["condition"])
                added, removed = folder_tags.apply(db, pid, int(actions["add_tag"]), int(row["storage_root_id"]), paths,
                                                   remove=True)  # known only through the policy: they follow the condition
                sub_added, sub_removed = sub_added + added, sub_removed + removed
        elif only_root_ids is None:
            sub_removed = db.execute(text("DELETE FROM folder_tags WHERE policy_id = :id"), {"id": pid}).rowcount or 0
    if actions.get("alert"):
        for row in matched.values():
            _raise_alert(db, policy, row, str((actions.get("alert") or {}).get("severity") or "warning"))
    resolved = _resolve_alerts(db, pid, gone_ids) if gone_ids else 0
    notified = _notify(db, policy, [matched[root_id] for root_id in new_ids]) if actions.get("notify_guardians") and new_ids else 0
    jobs = _due_jobs(db, pid, list(matched), actions.get("jobs") or {}, now) if allow_jobs else []
    if only_root_ids is None:
        db.execute(
            text("UPDATE governance_policies SET last_run_at = :now, last_matched = :matched, last_new = :new, last_error = NULL WHERE id = :id"),
            {"now": now, "matched": len(matched), "new": len(new_ids), "id": pid},
        )
    db.commit()
    return {"policy_id": pid, "matched": len(matched), "new": len(new_ids), "gone": len(gone_ids), "tagged": tagged, "untagged": untagged,
            "subfolders_tagged": sub_added, "subfolders_untagged": sub_removed,
            "resolved": resolved, "notified": notified, "jobs": jobs}


def run_all(db: Session, *, policy_id: int | None = None, only_root_ids: set[int] | None = None, trigger: str = "schedule",
            allow_jobs: bool = True) -> dict[str, Any]:
    """Evaluate the active policies. The tasks they ask for are returned in « jobs »: the caller hands them to
    the workers with dispatch_jobs (async), or use run_all_and_dispatch."""
    from app.services.activity_log import log_activity

    policies = [p for p in list_policies(db) if p["enabled"] and (policy_id is None or p["id"] == int(policy_id))]
    if not policies:
        return {"status": "success", "message": "Aucune politique active", "results": []}
    rows = folder_rows(db)
    results, failed = [], []
    for policy in policies:
        try:
            result = run_policy(db, policy, rows, only_root_ids=only_root_ids, allow_jobs=allow_jobs)
            results.append(result)
            if result["new"] or result["gone"] or result["jobs"]:
                log_activity(
                    None, actor_type="system", actor_id=None, actor_display="policies",
                    action="policy.applied", outcome="success", target_type="policy", target_id=str(policy["id"]),
                    target_display=policy["name"], context_json={**{k: v for k, v in result.items() if k != "jobs"}, "jobs": len(result["jobs"]), "trigger": trigger},
                )
        except Exception as exc:
            db.rollback()
            logger.exception("POLICY_RUN_FAILED", extra={"policy_id": policy["id"]})
            failed.append(policy["name"])
            db.execute(text("UPDATE governance_policies SET last_run_at = :now, last_error = :error WHERE id = :id"),
                       {"now": _now(), "error": str(exc)[:500], "id": policy["id"]})
            db.commit()
    matched = sum(r["matched"] for r in results)
    new = sum(r["new"] for r in results)
    jobs = [job for r in results for job in r["jobs"]]
    message = (f"{len(results)} politique(s) : {matched} dossier(s) concerné(s), {new} nouveau(x)"
               + (f", {len(jobs)} tâche(s) pour les workers" if jobs else "") + (f" · en échec : {', '.join(failed)}" if failed else ""))
    return {"status": "partial" if failed else "success", "message": message, "results": results, "jobs": jobs}


async def run_all_and_dispatch(db: Session, **kwargs: Any) -> dict[str, Any]:
    summary = run_all(db, **kwargs)
    # Corrections of passwords past their due date: their folders are scanned again (overdue if still there)
    try:
        from app.services import remediations

        rescans = [{"kind": "sensitivity", "storage_root_id": root_id, "policy_id": 0} for root_id in remediations.due_for_rescan(db)]
        if rescans:
            summary["jobs"] = [*(summary.get("jobs") or []), *rescans]
    except Exception:
        db.rollback()
        logger.warning("REMEDIATION_RESCAN_FAILED", exc_info=True)
    if summary.get("jobs"):
        summary["queued"] = await dispatch_jobs(db, summary["jobs"])
    summary["jobs"] = len(summary.get("jobs") or [])
    for result in summary.get("results") or []:
        result["jobs"] = len(result.get("jobs") or [])
    return summary


def forget_policy(db: Session, policy_id: int) -> None:
    """A deleted (or disabled) policy: its alerts close, its hits go. The tags it added stay."""
    _resolve_alerts(db, int(policy_id))
    db.execute(text("DELETE FROM governance_policy_hits WHERE policy_id = :id"), {"id": int(policy_id)})
    try:  # the tags it set on sub-folders follow it (they are only known through it)
        db.execute(text("DELETE FROM folder_tags WHERE policy_id = :id"), {"id": int(policy_id)})
    except Exception:
        db.rollback()
    db.commit()


# ---- storage of the policies (the routes hold no SQL) ----
def tag_exists(db: Session, tag_id: int) -> bool:
    return db.execute(text("SELECT 1 FROM tags WHERE id = :id"), {"id": int(tag_id)}).first() is not None


def hit_counts(db: Session) -> dict[int, int]:
    """{policy: folders it matches now}."""
    return {int(pid): int(count) for pid, count in db.execute(text("SELECT policy_id, COUNT(*) FROM governance_policy_hits GROUP BY policy_id")).all()}


def save_policy(db: Session, policy_id: int | None, *, name: str, description: str | None, enabled: bool, condition: str,
                actions: dict[str, Any], by: str | None) -> int:
    """Creates (policy_id None) or updates a policy; commits. Returns its id."""
    params = {"name": name.strip(), "description": description, "enabled": int(enabled), "condition": condition.strip(),
              "actions": json.dumps(actions), "by": by}
    if policy_id is None:
        result = db.execute(text("""INSERT INTO governance_policies (name, description, enabled, condition_query, actions_json, created_by, updated_by)
                                    VALUES (:name, :description, :enabled, :condition, :actions, :by, :by)"""), params)
        db.commit()
        return int(result.lastrowid)
    db.execute(text("""UPDATE governance_policies SET name = :name, description = :description, enabled = :enabled,
                         condition_query = :condition, actions_json = :actions, updated_by = :by WHERE id = :id"""), {**params, "id": int(policy_id)})
    db.commit()
    return int(policy_id)


def delete_policy(db: Session, policy_id: int) -> None:
    forget_policy(db, policy_id)
    db.execute(text("DELETE FROM governance_policies WHERE id = :id"), {"id": int(policy_id)})
    db.commit()
