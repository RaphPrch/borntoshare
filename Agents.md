# AGENTS.md

## Project: BornToShare

BornToShare is a data governance application with a SvelteKit frontend, FastAPI services, a gateway, a governance service, a DAL service, MariaDB, Keycloak/AD/local authentication, and capsule-based execution.

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
- Frontend must call the gateway using relative `/api/*` routes only.
- Frontend must not call DAL, auth-service, or governance-service directly.
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

Gateway:
- Gateway is the only public API entrypoint.
- Proxy `/api/auth/*` to auth-service.
- Proxy governance endpoints through `/api/governance/*`.
- Preserve session cookie behavior.
- Do not bypass the gateway.

Governance service:
- Governance contains business logic.
- Governance calls DAL for persistence.
- Governance must not access the database directly.

DAL service:
- DAL owns database access.
- Use SQLAlchemy 2.x and Alembic migrations.
- Do not put business workflow logic in DAL.

Auth:
- Keep `b2s_session` cookie behavior.
- Support local, AD, dev, and optional Keycloak.
- Do not force Keycloak-only authentication.

Access model:
- Use “Access Profiles”, not “Permission Packs”.
- Keep AD group names abstracted from the user-facing UI.
- Do not expose raw AD implementation details in the main user flow.

Capsules:
- Capsules are agentless.
- Windows execution uses WinRM.
- Linux execution uses SSH or remote commands.
- Capsule execution must remain isolated from the main application network.

## Credit-saving behavior

When possible:
- Read only the files needed for the task.
- Avoid broad repository searches.
- Avoid rewriting full files.
- Avoid verbose summaries.
- Prefer one small patch at a time.
- Ask for confirmation before large multi-service changes.