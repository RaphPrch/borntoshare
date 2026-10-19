# AGENTS.md

## Project: BornToShare

BornToShare is a data governance application with a SvelteKit frontend (which also acts as the API gateway), FastAPI services (auth, core, secret-broker, capsule-runner, wizard), MariaDB, Keycloak/AD/local authentication, and capsule-based execution.

## Working rules

Work in small, controlled changes.

Before modifying files:
- If the task touches more than 3 files, first provide a short plan.
- List the files you intend to modify.
- Do not modify files outside the requested scope.

Coding rules:
- Prefer minimal diffs.
- Do not perform global refactors unless explicitly requested.
- Do not rename components, routes, services, or API contracts unless explicitly requested.
- Do not change the visual theme unless requested.
- Do not remove existing behavior unless requested.
- Do not generate long explanations unless asked.

## Architecture rules

Frontend:
- SvelteKit SSR.
- Browser code must call relative `/api/*` routes only.
- Browser code must not call core-service or auth-service directly; the SvelteKit server (BFF) routes `/api/*` to them.
- Keep login and change-password pages in the frontend.
- Respect existing UI components and CSS tokens.
- Follow the `src/lib` layout and shared helpers described in `frontend-service/docs/structure.md`.
- No glassmorphism.
- Keep the BornToShare theme:
  - Background: #F5F7FB
  - Primary: #2F6FED to #1D4ED8
  - Success: #2EB88A
  - Border: #E5EAF3
  - Text: #0f172a
  - Topbar: deep blue gradient

Gateway (frontend BFF):
- There is no separate gateway service: the SvelteKit server is the only public API entrypoint.
- Routing of `/api/*` to auth-service or core-service lives in `frontend-service/src/lib/server/service-routes.ts`; service URLs come from `B2S_AUTH_URL`, `B2S_CORE_URL`. Orchestration paths (`/access-requests/bulk`, `/identity/{search,import,snapshots,jobs,discover}`, `/admin/jobs`, `/probes`) go to core-service under `/governance`.
- `/api/auth/*` goes to auth-service; `/api/internal/*` is never exposed.
- Preserve session cookie behavior.
- `ORIGIN` must be the public URL of the app: SvelteKit rejects cross-site form POSTs (CSRF) against it, and the principal cookie is `Secure` when it is HTTPS.

core-service (`core-service/`, all business data and orchestration):
- Layout of `app/`: `core/` (config, db, logging, errors, internal auth, `direct_call.py`, `values.py`), `data/` (`models/`, `repositories/`: all SQL), `services/` (business logic), `schemas/`, `api/` (routes, mounted under `/api`), `api/governance/` (orchestration routes, mounted under `/api/governance`), `jobs/` (Dramatiq broker, job contracts, QUEUED watchdog).
- Only `data/` and services touch the database. Use SQLAlchemy 2.x.
- Orchestration (`api/governance/`: access requests, identity imports, probes, AD groups) publishes provisioning jobs to Dramatiq. It calls route handlers directly (`core/direct_call.call_route`: own DB session, payload validated into the handler's model, no HTTP) or services; it never imports `app.data` or opens DB sessions, and only `app/main.py` mounts it (both enforced by `test_architecture_guardrails.py`).
- Service-to-service auth lives in `core/internal_auth.py` only (`X-Internal-Token` static/HMAC, `X-Service-Token` + scopes). Orchestration routes use `require_orchestration_access`; `B2S_ALLOW_PUBLIC_API` opens the non-`/internal/` ones to the BFF.
- Settings live in `core/config.py` only; `CAPSULE_BROKER_URL` is required at startup.
- Shared helpers: response envelopes `ui_data`/`ui_list`/`ui_action` (`api/_helpers.py`), value helpers (`core/values.py`), shared pydantic rules `SecretRefRules`/`ProbeStatusRules` (`schemas/common.py`). Reuse them instead of re-implementing.
- core-service never talks LDAP or SMB: directory and file-server work runs as capsule-runner jobs.

Auth:
- Keep `b2s_session` cookie behavior.
- Support local, AD, dev, and optional Keycloak.
- Do not force Keycloak-only authentication.
- Set `APP_ENV=prod` in production: auth-service and frontend refuse to start with the default `PRINCIPAL_SIGNING_KEY` (the principal cookie carries roles).

Access model:
- Use “Access Profiles”, not “Permission Packs”.
- Keep AD group names abstracted from the user-facing UI.
- Do not expose raw AD implementation details in the main user flow.

Capsules:
- Capsules are agentless.
- capsule-runner talks to targets over protocols only: LDAP/LDAPS (`ldap3`) for AD, SMB (Samba `smbclient`, `smbcacls`, `rpcclient`) for shares and NTFS ACLs, Kerberos (`kinit`) for tests. No WinRM, PowerShell or SSH.
- Capsule execution must remain isolated from the main application network.
- Job queue: Dramatiq over Redis. Redis is a standalone service (`redis/podman-compose.yml`), password-protected (`REDIS_PASSWORD`), with no published port, on the `bts-jobs` network shared only by core-service (publishes jobs) and capsule-runner (Dramatiq worker).
- Never put passwords on a command line: Samba tools (smbclient, smbcacls, rpcclient) go through `run_samba` (`capsule-runner/app/shared/samba_auth.py`), which uses a temporary auth file.

Database (MariaDB, SQL packs in `wizard-ui/backend/app/sql/`):
- There is no Alembic. `wizard-ui/backend/app/migrations_runner.py` applies `schema/` → `views/` → `indexes/` (and `seeds/` in dev); the logging DB has its own `logging/schema` + `logging/indexes`. Every file must be idempotent: the runner re-applies the whole pack.
- Tables: `CREATE TABLE IF NOT EXISTS`; columns added later go through an idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` in the same file. Indexes: `CREATE INDEX IF NOT EXISTS` in `indexes/020_indexes.sql`.
- Removing an object: delete its definition and add a `DROP ... IF EXISTS` to `schema/900_drop_unused_tables.sql`, `views/900_drop_unused_views.sql` or the "Removed indexes" section of `indexes/020_indexes.sql`, so existing databases converge. No one-shot migration scripts.
- Only create a view that code reads; `core-service/app/core/db.py` lists the views and columns checked at startup.
- Directory snapshots: only the active one and the previous archived one keep their user/group/membership rows (`DirectorySnapshotsRepo.purge_archived_details`).

Containers:
- One `Containerfile` per service; Python images follow the same template (`python:3.12-slim`, no venv, code owned by root, fixed non-root UID). `make build` / `make up` (root `Makefile`) start redis, then auth/secret-broker/core, then capsule-runner, then the frontend.

## Checks

Run before pushing (CI runs the same in `.github/workflows/ci.yml`):
- Python services: `python -m pytest -q` in each service directory (`wizard-ui/backend` for the wizard; auth-service needs `INTERNAL_TOKEN` set).
- Frontend (`frontend-service`): `npm run build`, the `npm run test:*` scripts, and `npm run check` (must not add type errors).

## Credit-saving behavior

When possible:
- Read only the files needed for the task.
- Avoid broad repository searches.
- Avoid rewriting full files.
- Avoid verbose summaries.
- Prefer one small patch at a time.
- Ask for confirmation before large multi-service changes.