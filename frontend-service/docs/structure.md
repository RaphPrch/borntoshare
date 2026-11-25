# Frontend structure (`src/lib`)

| Folder | Content |
|---|---|
| `api/` | One module per backend resource (`storage-roots.ts`, `zones.ts`…), all built on `api/client.ts` (browser side). |
| `api/http/` | Low-level HTTP: request, envelopes, `ApiError`. |
| `server/` | Server-only code: BFF proxy and routing to services, principal cookie, internal tokens, `require-auth.ts`. |
| `components/ui/` | Generic widgets: modals, empty states, tables, tabs, toaster, search field. |
| `components/entity/` | Building blocks of entity consoles (headers, drawers, KPI rows, alert strips, sidebars). |
| `components/layout/` | Shell of the v2 interface (no sidebar): `nav.ts` (the four menu sections by role and license, `buildNav`, `activeItem`, tested by `nav.test.ts`), `AppHeader` (☰ menu `NavMenu`, ⌘K search, bell), `ContextBar` (section › page, tabs of the entry via `SectionTabs`, main action), `GlobalSearch` (pages of `search-pages.ts`), `NotificationCenter`. Who may open which page: `utils/route-access.ts` (the layout redirects, tested by `route-access.test.ts`). |
| `components/<domain>/` | Domain components: `access-requests`, `activity`, `auth`, `dashboard` (Journal of the Dashboard), `identity`, `identity-sources`, `infrastructure`, `observability` (Governance Jobs), `pilot` (`pilot-engine.ts` of the Assistant, `/assistant`: questions turned into lists, unit-tested), `provisioning`, `settings`, `storage-endpoints`, `storage-roots`, `tags`, `zones`. The 5S screens live in `routes/(app)/five-s`. |
| `mappers/` | Pure functions turning API payloads into view models (unit-tested). |
| `stores/` | Svelte stores (toast, jobs, selection, snapshots, UI state). |
| `jobs/` | Background job and probe polling, probe runners. |
| `errors/` | `toAppError`, presenters, `reportUiError` / `toUiAppError` for UI failures. |
| `logging/` | Frontend logger and transports. |
| `activity/` | Activity event formatting (titles, severities, templates). |
| `utils/` | Shared helpers: `format.ts` (dates, initials, `timeAgo`), `values.ts` (`asRecord`, `normalizeText`, `clamp`, `sleep`), status labels, domain helpers. |
| `types/` | Shared TypeScript types. |
| `i18n/`, `styles/` | Translations, global CSS; `styles/v2.css` holds the shared classes of the v2 screens (`v2-head`, `v2-stats`, `v2-list`/`v2-row`, `v2-tabs`, `v2-band`, `v2-bulk`…). |

Rules:

- Before writing a date/initials/record helper, use `utils/format.ts` or `utils/values.ts`.
- Report UI action failures with `reportUiError` (`$lib/errors`) instead of re-implementing log + toast.
- Route-specific components stay next to their route (`src/routes/**/components/`); move them to `lib/components/<domain>/` once a second route uses them.
- Files under `lib/` imported by `*.test.ts` (run with `tsx`) use relative imports.
- `npm run check` must not add type errors; CI also rejects new unused CSS selectors (they are no longer silenced).
