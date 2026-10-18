# Frontend structure (`src/lib`)

| Folder | Content |
|---|---|
| `api/` | One module per backend resource (`storage-roots.ts`, `zones.ts`…), all built on `api/client.ts` (browser side). |
| `api/http/` | Low-level HTTP: request, envelopes, `ApiError`. |
| `server/` | Server-only code: BFF proxy and routing to services, principal cookie, internal tokens, `require-auth.ts`. |
| `components/ui/` | Generic widgets: modals, empty states, tables, tabs, toaster, search field. |
| `components/entity/` | Building blocks of entity consoles (headers, drawers, KPI rows, alert strips, sidebars). |
| `components/<domain>/` | Domain components: `access-requests`, `activity`, `dashboard`, `identity`, `identity-sources`, `jobs` (probe UI), `layout`, `provisioning`, `settings`, `storage-endpoints`, `storage-roots`, `tags`, `zones`. |
| `mappers/` | Pure functions turning API payloads into view models (unit-tested). |
| `stores/` | Svelte stores (toast, jobs, selection, snapshots, UI state). |
| `jobs/` | Background job and probe polling, probe runners. |
| `errors/` | `toAppError`, presenters, `reportUiError` / `toUiAppError` for UI failures. |
| `logging/` | Frontend logger and transports. |
| `activity/` | Activity event formatting (titles, severities, templates). |
| `utils/` | Shared helpers: `format.ts` (dates, initials, `timeAgo`), `values.ts` (`asRecord`, `normalizeText`, `clamp`, `sleep`), status labels, domain helpers. |
| `types/` | Shared TypeScript types. |
| `i18n/`, `styles/` | Translations, global CSS. |

Rules:

- Before writing a date/initials/record helper, use `utils/format.ts` or `utils/values.ts`.
- Report UI action failures with `reportUiError` (`$lib/errors`) instead of re-implementing log + toast.
- Route-specific components stay next to their route (`src/routes/**/components/`); move them to `lib/components/<domain>/` once a second route uses them.
- Files under `lib/` imported by `*.test.ts` (run with `tsx`) use relative imports.
- `npm run check` must not add type errors; CI also rejects new unused CSS selectors (they are no longer silenced).
