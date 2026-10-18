# AGENTS.md

## Project: BornToShare

BornToShare is a data governance application with a SvelteKit frontend (which also acts as the API gateway), FastAPI services (auth, governance, DAL, secret-broker, capsule-runner, wizard), MariaDB, Keycloak/AD/local authentication, and capsule-based execution.

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
- Browser code must not call DAL, auth-service, or governance-service directly; the SvelteKit server (BFF) routes `/api/*` to them.
- Keep login and change-password pages in the frontend.
- Respect existing UI components and CSS tokens.
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
- Routing of `/api/*` to auth-service, DAL or governance lives in `frontend-service/src/lib/server/service-routes.ts`; service URLs come from `B2S_AUTH_URL`, `B2S_DAL_URL`, `B2S_GOVERNANCE_URL`.
- `/api/auth/*` goes to auth-service; `/api/internal/*` is never exposed.
- Preserve session cookie behavior.
- `ORIGIN` must be the public URL of the app: SvelteKit rejects cross-site form POSTs (CSRF) against it, and the principal cookie is `Secure` when it is HTTPS.

Governance service:
- Governance contains business logic.
- Governance calls DAL for persistence.
- DAL never calls governance (no circular dependency; enforced by `test_dal_never_calls_governance`).
- Governance must not access the database directly.

DAL service:
- DAL owns database access.
- Use SQLAlchemy 2.x. There is no Alembic: the SQL schema, views and seeds are owned by wizard-ui (`wizard-ui/backend/app/sql/`) and applied by its migrations runner.
- Do not put business workflow logic in DAL.

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
- Never put passwords on a command line: Samba tools (smbclient, smbcacls, rpcclient) go through `run_samba` (`capsule-runner/app/shared/samba_auth.py`), which uses a temporary auth file.

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