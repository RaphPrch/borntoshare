<script module lang="ts">
  import { recall, remember } from '$lib/utils/remember';
  type Quick = 'all' | 'review' | 'guard' | 'never' | 'failed' | 'sensitive' | 'quota';
  type Sort = 'todo' | 'size' | 'quota' | 'score' | 'name';
  // Kept in this browser: the list reopens with the same filter, sort and page size
  const memory = recall('storage-roots-v2', { quick: 'all' as Quick, sort: 'todo' as Sort, pageSize: 25 });
</script>

<script lang="ts">
  import TagQuickEdit from './TagQuickEdit.svelte';
  import Sparkline from '$lib/components/ui/Sparkline.svelte';
  import { onMount } from 'svelte';
  import { t } from '$lib/i18n';
  import { apiGetData } from '$lib/api/client';
  import { fivesEnabled, governanceEnabled } from '$lib/utils/features';
  import { formatBytes } from '$lib/utils/format';
  import type { StorageRootRow } from '$lib/utils/storage-roots';
  import { matchesFolderQuery, parseFolderQuery } from '$lib/components/storage-roots/folder-query';
  import StorageRootContextMenu, { type FolderMenuExtra } from '$lib/components/storage-roots/StorageRootContextMenu.svelte';
  import type { FolderActionKind } from '$lib/components/storage-roots/StorageRootFolderActions.svelte';
  import { menuPositionFor } from '$lib/components/ui/ContextMenu.svelte';
  import StorageRootSidePeek from '$lib/components/storage-roots/StorageRootSidePeek.svelte';

  interface Props {
    /**
     * v2 list of the storage roots, next to the tree: one line per folder with what BornToShare measures
     * (volume and quota, 5S, sensitivity, tags, state). Quick filters, sort, pages, a selection to act on
     * several folders, and on each line the ⋯ / right-click menu of every action.
     */
    rows?: StorageRootRow[];
    query?: string;
    isAdmin?: boolean;
    onQueryChange?: (value: string) => void;
    onOpenRoot?: (id: number) => void;
    onFolderAction?: ((kind: FolderActionKind, row: StorageRootRow) => void) | null;
    onExtra?: ((key: FolderMenuExtra, row: StorageRootRow) => void) | null;
    onBulkAnalysis?: ((kind: 'sensitivity' | 'measure', rows: StorageRootRow[]) => Promise<void> | void) | null;
  }

  let { rows = [], query = '', isAdmin = false, onQueryChange = () => {}, onOpenRoot = () => {}, onFolderAction = null, onExtra = null,
    onBulkAnalysis = null }: Props = $props();

  type R = Record<string, any>;
  const num = (value: unknown): number | null => (value == null || value === '' || !Number.isFinite(Number(value)) ? null : Number(value));
  const id = (row: R) => Number(row?.storage_root_id ?? 0);

  // ---- 5S figures (size, score) of the module, when it runs ----
  let fives = $state(new Map<number, { size: number | null; score: number | null }>());
  let trends = $state<Record<string, number[]>>({});
  const trendTitle = (points: number[]) => points.length > 1
    ? t('{count} measures: {from} → {to}', { count: points.length, from: formatBytes(points[0]), to: formatBytes(points[points.length - 1]) }) : '';
  onMount(() => {
    if (!$fivesEnabled) return;
    void apiGetData<{ folders: Array<{ id: number; size_bytes: number | null; score: number | null }> }>(fetch, '/modules/fives/five-s')
      .then((data) => (fives = new Map((data?.folders ?? []).map((f) => [Number(f.id), { size: num(f.size_bytes), score: num(f.score) }]))))
      .catch(() => null);
    // The volume at the last measures: a trend line next to the volume
    void apiGetData<Record<string, number[]>>(fetch, '/modules/fives/sparklines').then((data) => (trends = data ?? {})).catch(() => null);
  });

  const sizeOf = (row: R): number | null => fives.get(id(row))?.size ?? num(row.content_size_bytes) ?? num(row.estimated_size_bytes) ?? num(row.quota_used_bytes);
  const scoreOf = (row: R): number | null => fives.get(id(row))?.score ?? null;
  const measured = (row: R) => sizeOf(row) != null || ['done', 'running'].includes(String(row.measure_status ?? ''));
  const failed = (row: R) => String(row.measure_status ?? '') === 'failed';
  const secrets = (row: R) => Number(row.password_files ?? 0) + Number(row.key_files ?? 0);
  const quotaPct = (row: R): number | null => num(row.quota_used_percent);
  const alerts = (row: R) => Number(row.open_alerts_count ?? 0);
  const noGuardian = (row: R) => $governanceEnabled && Number(row.guardians_count ?? 0) === 0;

  type State = { label: string; tone: 'ok' | 'warn' | 'bad' | 'mut' | 'info'; rank: number };
  function stateOf(row: R): State {
    const measure = String(row.measure_status ?? '');
    if (measure === 'running' || measure === 'queued') return { label: t('Measuring'), tone: 'info', rank: 5 };
    if (failed(row)) return { label: t('Measure failed'), tone: 'bad', rank: 0 };
    if (Number(row.open_alerts_error_count ?? 0) > 0) return { label: t('{count} alert(s)', { count: alerts(row) }), tone: 'bad', rank: 0 };
    if (noGuardian(row)) return { label: t('No guardian'), tone: 'bad', rank: 1 };
    if (alerts(row) > 0) return { label: t('{count} alert(s)', { count: alerts(row) }), tone: 'warn', rank: 2 };
    if (!measured(row)) return { label: t('Never measured'), tone: 'mut', rank: 3 };
    return { label: t('Compliant'), tone: 'ok', rank: 4 };
  }
  function sensitivityOf(row: R): { label: string; tone: 'ok' | 'warn' | 'bad' | 'mut' | 'info' } {
    const status = String(row.sensitivity_status ?? '');
    if (status === 'running' || status === 'queued') return { label: t('Scanning'), tone: 'info' };
    if (row.sensitive_files == null && !status) return { label: t('Not scanned'), tone: 'mut' };
    if (Number(row.password_files ?? 0) > 0) return { label: t('{count} password file(s)', { count: Number(row.password_files) }), tone: 'bad' };
    if (Number(row.key_files ?? 0) > 0) return { label: t('{count} key file(s)', { count: Number(row.key_files) }), tone: 'bad' };
    if (Number(row.personal_files ?? 0) > 0) return { label: t('{count} personal data', { count: Number(row.personal_files) }), tone: 'warn' };
    if (Number(row.sensitive_files ?? 0) > 0) return { label: t('{count} flagged', { count: Number(row.sensitive_files) }), tone: 'warn' };
    return { label: t('Nothing found'), tone: 'ok' };
  }
  const ringTone = (score: number | null) => (score == null ? '#d5dee6' : score >= 80 ? '#138a5c' : score >= 60 ? '#c27a12' : '#d0435a');
  const C13 = 2 * Math.PI * 13;

  // ---- filters, sort, pages ----
  let quick = $state<Quick>(memory.quick);
  let sort = $state<Sort>(memory.sort);
  let pageSize = $state<number>(memory.pageSize);
  let pageIndex = $state(0);
  $effect.pre(() => remember('storage-roots-v2', { quick, sort, pageSize }));

  const QUICK: Array<{ key: Quick; label: () => string; test: (row: R) => boolean; governance?: boolean }> = [
    { key: 'all', label: () => t('All'), test: () => true },
    { key: 'review', label: () => t('To review'), test: (row) => alerts(row) > 0 || failed(row) },
    { key: 'guard', label: () => t('No guardian'), test: noGuardian, governance: true },
    { key: 'never', label: () => t('Never measured'), test: (row) => !measured(row) },
    { key: 'failed', label: () => t('Measure failed'), test: failed },
    { key: 'sensitive', label: () => t('Sensitive'), test: (row) => secrets(row) > 0 },
    { key: 'quota', label: () => t('Quota > 85 %'), test: (row) => (quotaPct(row) ?? 0) > 85 }
  ];
  let quicks = $derived(QUICK.filter((q) => !q.governance || $governanceEnabled));
  let parsed = $derived(parseFolderQuery(query));
  // « key:value » filters, then the free text on the name, the paths and the server
  let words = $derived(parsed.text.toLowerCase().split(/\s+/).filter(Boolean));
  let searched = $derived(rows.filter((row) => matchesFolderQuery(row, parsed.filters) && (!words.length || words.every((word) =>
    `${row.storage_root_name ?? ''} ${row.storage_root_code ?? ''} ${row.root_path ?? ''} ${row.dfs_path ?? ''} ${row.storage_endpoint_name ?? ''} ${row.zone_name ?? ''}`
      .toLowerCase().includes(word)))));
  let filtered = $derived.by(() => {
    const test = QUICK.find((q) => q.key === quick)?.test ?? (() => true);
    const list = searched.filter(test);
    const byName = (a: R, b: R) => String(a.storage_root_name ?? '').localeCompare(String(b.storage_root_name ?? ''), 'fr');
    return list.slice().sort((a, b) => {
      if (sort === 'name') return byName(a, b);
      if (sort === 'size') return (sizeOf(b) ?? -1) - (sizeOf(a) ?? -1);
      if (sort === 'quota') return (quotaPct(b) ?? -1) - (quotaPct(a) ?? -1);
      if (sort === 'score') return (scoreOf(a) ?? 999) - (scoreOf(b) ?? 999);
      return stateOf(a).rank - stateOf(b).rank || (sizeOf(b) ?? -1) - (sizeOf(a) ?? -1);
    });
  });
  let pages = $derived(Math.max(1, Math.ceil(filtered.length / pageSize)));
  let page = $derived(Math.min(pageIndex, pages - 1));
  let shown = $derived(filtered.slice(page * pageSize, page * pageSize + pageSize));
  let maxSize = $derived(Math.max(1, ...searched.map((row) => sizeOf(row) ?? 0)));
  let totalSize = $derived(searched.reduce((sum, row) => sum + (sizeOf(row) ?? 0), 0));
  let servers = $derived(new Set(searched.map((row) => String(row.storage_endpoint_name ?? ''))).size);

  // ---- selection ----
  let selected = $state(new Set<number>());
  let allShown = $derived(shown.length > 0 && shown.every((row) => selected.has(id(row))));
  function toggle(row: R) {
    const next = new Set(selected);
    if (next.has(id(row))) next.delete(id(row));
    else next.add(id(row));
    selected = next;
  }
  function toggleAll() {
    const next = new Set(selected);
    for (const row of shown) {
      if (allShown) next.delete(id(row));
      else next.add(id(row));
    }
    selected = next;
  }
  async function bulk(kind: 'measure' | 'sensitivity') {
    const chosen = rows.filter((row) => selected.has(id(row)));
    await onBulkAnalysis?.(kind, chosen);
    selected = new Set();
  }

  // ---- side preview: « Preview » and a click on the name open it here; the other entries go to the page ----
  let peekRow = $state<StorageRootRow | null>(null);
  const extra = (key: FolderMenuExtra, row: StorageRootRow) => {
    if (key === 'peek') peekRow = row;
    else {
      peekRow = null;
      onExtra?.(key, row);
    }
  };

  // ---- menu ----
  let menuRow = $state<StorageRootRow | null>(null);
  let menuAt = $state({ x: 0, y: 0 });
  const openMenu = (row: StorageRootRow) => (event: MouseEvent) => {
    event.preventDefault();
    event.stopPropagation();
    menuAt = menuPositionFor(event);
    menuRow = row;
  };

  const SORTS: Array<{ key: Sort; label: () => string }> = [
    { key: 'todo', label: () => t('To handle first') },
    { key: 'size', label: () => t('Largest') },
    { key: 'quota', label: () => t('Fullest quota') },
    { key: 'score', label: () => t('Lowest 5S score') },
    { key: 'name', label: () => t('Name (A → Z)') }
  ];
</script>

<div class="v2-main srl">
  <div class="v2-tool">
    <div class="v2-scope">{parsed.filters.length || parsed.text ? t('Search results') : t('All the folders')}
      <small>{t('{count} folder(s) · {servers} server(s)', { count: searched.length, servers })}{#if totalSize} · {formatBytes(totalSize)}{/if}</small></div>
    <div class="srl__tools">
      <label class="v2-search srl__q"><i class="bi bi-search" aria-hidden="true"></i>
        <input type="search" value={query} oninput={(event) => { onQueryChange((event.currentTarget as HTMLInputElement).value); pageIndex = 0; }}
          placeholder={t('Name, path… or tag:, gardien:, zone:, serveur:, est:')} aria-label={t('Search a folder')} /></label>
      <select class="b2s-input srl__sort" bind:value={sort} aria-label={t('Sort')}>
        {#each SORTS as option (option.key)}<option value={option.key}>{option.label()}</option>{/each}
      </select>
    </div>
    <div class="v2-seg srl__quick" role="group" aria-label={t('Quick filters')}>
      {#each quicks as q (q.key)}
        <button type="button" class:is-on={quick === q.key} aria-pressed={quick === q.key} onclick={() => { quick = q.key; pageIndex = 0; }}>{q.label()} <b>{searched.filter(q.test).length}</b></button>
      {/each}
    </div>
  </div>

  {#if selected.size}
    <div class="v2-bulk" role="region" aria-label={t('Actions on the selection')}>
      <span><b>{selected.size}</b> {t('selected')}</span>
      {#if onBulkAnalysis}
        <button type="button" class="is-pri" onclick={() => bulk('measure')}><i class="bi bi-rulers" aria-hidden="true"></i> {t('Measure')}</button>
        <button type="button" onclick={() => bulk('sensitivity')}><i class="bi bi-shield-lock" aria-hidden="true"></i> {t('Scan the sensitivity')}</button>
      {/if}
      <button type="button" style="margin-left: auto" onclick={() => (selected = new Set())}>{t('Cancel')}</button>
    </div>
  {/if}

  <div class="v2-list" role="table" aria-label={t('Folders')}>
    <div class="v2-row is-head srl__g" role="row">
      <input type="checkbox" checked={allShown} onchange={toggleAll} aria-label={t('Select the page')} />
      <button type="button" onclick={() => (sort = 'name')}>{t('Folder')}{sort === 'name' ? ' ↓' : ''}</button>
      <span>{t('Server')}</span>
      <button type="button" onclick={() => (sort = 'size')}>{t('Volume · quota')}{sort === 'size' ? ' ↓' : ''}</button>
      <button type="button" onclick={() => (sort = 'score')}>5S{sort === 'score' ? ' ↑' : ''}</button>
      <span>{t('Sensitivity')}</span>
      <span>{t('Tags')}</span>
      <span>{t('State')}</span>
      <span></span>
    </div>
    {#each shown as row (id(row))}
      {@const size = sizeOf(row)}
      {@const pct = quotaPct(row)}
      {@const score = scoreOf(row)}
      {@const state = stateOf(row)}
      {@const sens = sensitivityOf(row)}
      {@const tags = (Array.isArray(row.tags) ? row.tags : []) as R[]}
      <div class="v2-row srl__g" class:is-picked={selected.has(id(row))} role="row" tabindex="-1" oncontextmenu={openMenu(row)}>
        <input type="checkbox" checked={selected.has(id(row))} onchange={() => toggle(row)} aria-label={t('Select {name}', { name: String(row.storage_root_name ?? '') })} />
        <div class="v2-nm">
          <button type="button" onclick={() => (peekRow = row)}>{row.storage_root_name ?? row.storage_root_code}</button>
          <small title={String(row.dfs_path ?? row.root_path ?? '')}>{row.dfs_path ?? row.root_path ?? ''}</small>
        </div>
        <div class="v2-nm"><span>{row.storage_endpoint_name ?? '—'}</span><span class="v2-sub">{row.zone_name ?? ''}</span></div>
        <div class="srl__vol">
          <span>{#if trends[String(id(row))]}<Sparkline points={trends[String(id(row))]} title={trendTitle(trends[String(id(row))])} />{/if}
            {size != null ? formatBytes(size) : '—'}{#if pct != null} <small>· {pct} % {t('of')} {formatBytes(Number(row.quota_limit_bytes ?? 0))}</small>{/if}</span>
          <div class="v2-bar" class:is-ok={pct != null && pct < Number(row.quota_warn_percent ?? 85)} class:is-warn={pct != null && pct >= Number(row.quota_warn_percent ?? 85) && pct < 100} class:is-bad={pct != null && pct >= 100}>
            <i style={`width: ${pct != null ? Math.min(100, pct) : Math.max(3, Math.round(((size ?? 0) / maxSize) * 100))}%`}></i>
          </div>
        </div>
        <div class="srl__ring" role="img" aria-label={t('5S score {value}', { value: score ?? '—' })}>
          <svg viewBox="0 0 34 34" aria-hidden="true"><circle cx="17" cy="17" r="13" fill="none" stroke="#eaeff3" stroke-width="4"></circle>
            <circle cx="17" cy="17" r="13" fill="none" stroke={ringTone(score)} stroke-width="4" stroke-linecap="round"
              stroke-dasharray={`${((C13 * (score ?? 0)) / 100).toFixed(1)} ${C13.toFixed(1)}`}></circle></svg>
          <span>{score ?? '—'}</span>
        </div>
        <span><span class={`v2-tag is-${sens.tone}`}>{sens.label}</span></span>
        <div class="srl__tags">
          {#each tags.slice(0, 2) as tag, index (index)}<span class="srl__tg">{tag.label ?? tag.name ?? tag.tag_name}</span>{/each}
          {#if tags.length > 2}<span class="srl__tg">+{tags.length - 2}</span>{/if}
          {#if Array.isArray(row.subfolder_tags) && row.subfolder_tags.length}<span class="srl__tg is-auto" title={t('Tags of its sub-folders, set by the policies')}>⚡ {row.subfolder_tags.length}</span>{/if}
          <TagQuickEdit rootId={id(row)} {tags} onChange={(next) => (row.tags = next)} />
        </div>
        <span><span class={`v2-tag is-${state.tone}`}>{state.label}</span></span>
        <button type="button" class="v2-dots" aria-label={t('Actions on {name}', { name: String(row.storage_root_name ?? '') })} title={t('Actions on {name}', { name: String(row.storage_root_name ?? '') })} onclick={openMenu(row)}><i class="bi bi-three-dots" aria-hidden="true"></i></button>
      </div>
    {:else}
      <div class="v2-empty">{t('No folder matches.')} <button type="button" class="b2s-link-btn" onclick={() => { quick = 'all'; onQueryChange(''); }}>{t('Clear the filters')}</button></div>
    {/each}
  </div>

  <div class="v2-pager">
    <span>{filtered.length ? `${page * pageSize + 1}–${Math.min(filtered.length, (page + 1) * pageSize)} ${t('of')} ${filtered.length}` : t('No folder')}</span>
    <span class="v2-hint">{t('Right click on a line: measure, sensitivity, permissions, quota, tags, sub-folder…')}</span>
    <div class="v2-pager__r">
      <select class="b2s-input" bind:value={pageSize} onchange={() => (pageIndex = 0)} aria-label={t('Lines per page')}>
        <option value={25}>25</option><option value={50}>50</option><option value={100}>100</option>
      </select>
      <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" disabled={page === 0} onclick={() => (pageIndex = page - 1)} aria-label={t('Previous page')}>‹</button>
      <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" disabled={page >= pages - 1} onclick={() => (pageIndex = page + 1)} aria-label={t('Next page')}>›</button>
    </div>
  </div>
</div>

<StorageRootContextMenu row={menuRow} at={menuAt} onClose={() => (menuRow = null)}
  onAction={(kind, row) => onFolderAction?.(kind, row)} canManage={isAdmin && Boolean(onFolderAction)} onExtra={extra} />

<StorageRootSidePeek row={peekRow} score={peekRow ? scoreOf(peekRow) : null} {isAdmin} onClose={() => (peekRow = null)}
  onOpen={(rootId) => { peekRow = null; onOpenRoot(rootId); }}
  onAnalysis={onBulkAnalysis ? (kind, row) => void onBulkAnalysis?.(kind, [row]) : null} onExtra={extra} />

<style>
  .srl { border: 1px solid var(--b2s-color-border-soft); border-radius: 16px; background: #fff; overflow: hidden; }
  .srl .v2-bulk { top: 70px; }
  .srl__tools { margin-left: auto; display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
  .srl__q { min-width: 300px; }
  .srl__sort { width: auto; height: 36px; }
  .srl__quick { width: 100%; }
  .srl__g { grid-template-columns: 22px minmax(210px, 2fr) minmax(110px, 0.9fr) 170px 40px 150px minmax(120px, 1.1fr) 130px 36px; min-width: 1120px; }
  .srl__vol { display: flex; flex-direction: column; gap: 5px; font-size: 13px; font-weight: 500; }
  .srl__vol small { color: var(--b2s-color-text-muted); font-size: 11.5px; font-weight: 400; }
  .srl__vol .v2-bar { height: 5px; }
  .srl__ring { position: relative; width: 34px; height: 34px; }
  .srl__ring svg { width: 34px; height: 34px; transform: rotate(-90deg); }
  .srl__ring span { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; font-size: 10.5px; font-weight: 700; }
  .srl__tags { display: flex; flex-wrap: wrap; gap: 4px; min-width: 0; }
  .srl__tg { padding: 2px 7px; border-radius: 6px; background: var(--b2s-color-surface-muted); color: var(--b2s-color-text-soft); font-size: 11px; font-weight: 600; white-space: nowrap; }
  .srl__tg.is-auto { background: var(--b2s-accent-soft); color: var(--b2s-accent-strong); }
  .v2-pager select { width: auto; height: 32px; }
</style>
