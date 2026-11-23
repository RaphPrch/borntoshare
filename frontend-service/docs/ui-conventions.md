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
| Page head, figures, list of a v2 screen | classes of `styles/v2.css`: `v2-head`, `v2-stats`/`v2-stat`, `v2-list`/`v2-row`, `v2-pager`, `v2-bulk` |
| Layout of a page | grey page, white cards: each `v2-sec` is a card (not inside a `v2-ws`, which is already one); `v2-stat` is a KPI card, optional icon first: `<i class="bi bi-… [is-warn\|is-bad\|is-info]">` |
| Status pill | `StatusBadge`; `v2-tag` and `sg-tag` have the same size and colors (soft background, `-border`, `-strong` text) |
| Motion | `MOTION` / `pop` / `dur` from `utils/motion.ts` for a panel that opens (`in:pop`, `out:fade`), `slide` for one that unfolds; hover and selection transitions, keyboard focus ring and `<details>` animation are global in `app.css` (« Micro-interactions »), all off under `prefers-reduced-motion` |
| Filter or tab selected | teal: `v2-seg`, `sg-seg`, `SegmentedFilter` filled; `v2-tabs` underlined; a selected card or chip gets `--b2s-accent` border, never the text color |
| Several pages under one menu entry | `tabs` of the item in `layout/nav.ts` (drawn by `SectionTabs`), not a tab bar in the page |
| Right-click on a row (folder, job, tag, policy, identity…) | `ContextMenu` with the row's actions; the same actions stay reachable by a visible button (`⋯`) |
| Loading | `LoadingState`: inline spinner in a line; in a panel, list or drawer a skeleton (`block`, `skeleton="rows"` or `"detail"`) |

Behaviour:

- `Create` uses a modal, `Edit` a drawer for richer objects, `Delete` a short centered confirm modal in the danger style.
- Drawer header: title « Edit <object> », subtitle the name of the object being edited (a sentence only when creating).
- Footer: « Cancel » is always `b2s-btn-secondary`, the main action `b2s-btn-primary` with its icon (`bi-check2` to save);
  no section numbers in a form that is not a wizard, no line repeating the choice already shown by a selected card.
- Report a failed action with `reportUiError` (`$lib/errors`): it reads the business code behind the BFF
  (`upstreamErrorOf`) and shows the translated message of the service, never a generic status text.
- Every visible text goes through `t('English sentence')` with its French entry in `i18n/locales/fr.json`.
- Every audited event has a wording in `activity/templates.ts` (a core test checks it).
- Desktop only: no mobile layout.
- Prefer the CSS tokens (`--b2s-color-*`, `--b2s-radius-*`, `--b2s-fs-*`, `--b2s-focus-ring`) to hard-coded colors.

## Colors

Theme « teal / petrol », defined once in `styles/tokens.css` (the installer `wizard-ui/backend/app/static/style.css` repeats the same values).
Pick a color by its role, never by its look:

| Role | Token |
|---|---|
| Primary action, selected item, active tab, link | `--b2s-accent` (white text on it), hover `--b2s-accent-strong` |
| Selected row, soft highlight | `--b2s-accent-soft` (+ `--b2s-accent-border`) |
| Icon, marker, progress, focus outline (never text) | `--b2s-accent-vivid`; focus halo `--b2s-focus-ring` |
| Dark surface: top bar, bulk-action bar, tooltip, code | `--b2s-topbar-bg` (+ `-hover`, `-line`, `-muted` on it) |
| Brand green: logo, login headline only, dark text on it | `--b2s-brand` |
| Page / card / quiet background | `--b2s-bg` / `--b2s-color-surface` / `--b2s-color-surface-soft`, `-muted` |
| Text | `--b2s-color-heading`, `-text`, `-text-soft`, `-text-muted`, `-text-faint` |
| States | `--b2s-color-{success,warning,danger,info}` + `-strong` (text), `-soft` (background), `-border` |

Data colors stay outside the theme: tag colors (`utils/tag-colors.ts`), group / SSO purple, zone and server icons.
SVG presentation attributes (`stroke=`, `fill=`) do not read CSS variables: set the color in CSS (`currentColor`) or reuse the token value.
