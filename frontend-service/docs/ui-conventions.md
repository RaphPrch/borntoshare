# UI conventions

One element, one shared component or class. Before styling something locally, use these:

| Need | Use |
|---|---|
| Text field, select, textarea | class `b2s-input` (40 px, theme focus ring, `.is-invalid`, disabled) |
| Button | `b2s-btn` + `b2s-btn-primary` / `-secondary` / `-ghost` / `-danger-outline` / `-sm`; or `EntityActionButton` |
| Button that reads as a link (« Modifier › ») | class `b2s-link-btn` |
| Choice among a few (Tous · Gérés · …) | `SegmentedFilter` (`bind:value`, optional counts) |
| State pill | `StatusBadge` (`variant`: success, warning, error, info, muted; `compact`, `showDot`) |
| Figures at the top of an entity | classes `b2s-stat-tiles`, `b2s-stat-tile`, `b2s-stat-bar` |
| Long list | `ShowMore` (a page at a time) or the table footer « N of M » with a secondary button |
| Empty list | `EmptyStateInline` (one sentence) or `EmptyState` (title, text, action) |
| Confirmation | `ConfirmActionModal` / `ConfirmDeleteDialog`; a final deletion asks to type the name (`confirmName`) |

Behaviour:

- `Create` uses a modal, `Edit` a drawer for richer objects, `Delete` a short centered confirm modal in the danger style.
- Report a failed action with `reportUiError` (`$lib/errors`): it reads the business code behind the BFF
  (`upstreamErrorOf`) and shows the translated message of the service, never a generic status text.
- Every visible text goes through `t('English sentence')` with its French entry in `i18n/locales/fr.json`.
- Every audited event has a wording in `activity/templates.ts` (a core test checks it).
- Desktop only: no mobile layout.
- Prefer the CSS tokens (`--b2s-color-*`, `--b2s-radius-*`, `--b2s-fs-*`, `--b2s-focus-ring`) to hard-coded colors.
