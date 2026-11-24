<script lang="ts">
  import FileSearch from '../FileSearch.svelte';
  import { onMount, untrack } from 'svelte';
  import Pagination from '$lib/components/ui/Pagination.svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { apiGetData, apiPostData } from '$lib/api/client';
  import { formatBytes, formatDate, timeAgo } from '$lib/utils/format';
  import { csvFilename, downloadCsv } from '$lib/utils/csv';
  import { t } from '$lib/i18n';
  import { toast } from '$lib/stores/toast';
  import { reportUiError } from '$lib/errors';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import Sparkline from '$lib/components/ui/Sparkline.svelte';
  import ContextMenu, { menuPositionFor, type ContextMenuItem } from '$lib/components/ui/ContextMenu.svelte';
  import { park, placeOf, toneOf, type ParkFolder } from './explore-state.svelte';

  /**
   * Explorer, entry: the measured folders of the scope chosen in the tree (all, a zone, a server), with their trend,
   * the room their duplicates take, their sensitive files and their 5S score. A folder opens its content.
   */
  let zone = $derived($page.url.searchParams.get('zone'));
  let server = $derived($page.url.searchParams.get('server'));
  let isAdmin = $derived(Boolean(($page.data as any)?.me?.is_admin));

  let trends = $state<Record<string, number[]>>({});
  onMount(() => {
    void apiGetData<Record<string, number[]>>(fetch, '/modules/fives/sparklines').then((data) => (trends = data ?? {})).catch(() => null);
  });

  const DAY = 86_400_000;
  const measuredAt = (f: ParkFolder) => (f.measured_at ? Date.parse(f.measured_at) : NaN);
  const trendOf = (f: ParkFolder) => trends[String(f.id)] ?? [];
  const CHIPS = (): Array<{ key: string; label: string; test: (f: ParkFolder) => boolean }> => [
    { key: 'low', label: t('Score under 60'), test: (f) => f.score != null && f.score < 60 },
    { key: 'sensitive', label: t('With sensitive files'), test: (f) => (f.sensitive_files ?? 0) > 0 },
    { key: 'dups', label: t('With duplicates'), test: (f) => (f.dup_bytes ?? 0) > 0 },
    { key: 'growing', label: t('Growing'), test: (f) => { const p = trendOf(f); return p.length > 1 && p[p.length - 1] > p[0] * 1.05; } },
    { key: 'stale', label: t('Not measured for 30 days'), test: (f) => !(Date.now() - measuredAt(f) <= 30 * DAY) }
  ];
  let chips = $state<Record<string, boolean>>({});

  type SortKey = 'name' | 'size' | 'dup' | 'sensitive' | 'measured' | 'score';
  let sortKey = $state<SortKey>('size');
  let sortDesc = $state(true);
  const SORTS: Record<SortKey, (f: ParkFolder) => number | string> = {
    name: (f) => f.name.toLowerCase(), size: (f) => f.size_bytes ?? -1, dup: (f) => f.dup_bytes ?? -1, sensitive: (f) => f.sensitive_files ?? 0,
    measured: (f) => measuredAt(f) || 0, score: (f) => f.score ?? -1
  };
  function sortBy(key: SortKey) {
    if (sortKey === key) sortDesc = !sortDesc;
    else { sortKey = key; sortDesc = key !== 'name'; }
  }

  let inScope = $derived(park.folders.filter((f) => (!zone || placeOf(f.zone) === zone) && (!server || placeOf(f.server) === server)));
  let shown = $derived.by(() => {
    const active = CHIPS().filter((chip) => chips[chip.key]);
    const read = SORTS[sortKey];
    return inScope.filter((f) => active.every((chip) => chip.test(f))).sort((a, b) => {
      const x = read(a), y = read(b);
      return (x < y ? -1 : x > y ? 1 : 0) * (sortDesc ? -1 : 1);
    });
  });
  // A page at a time (the selection still covers every folder shown by the filters)
  let listPage = $state(1);
  let pageSize = $state(50);
  let paged = $derived(shown.slice((listPage - 1) * pageSize, listPage * pageSize));
  $effect.pre(() => {
    void shown.length;
    untrack(() => { if ((listPage - 1) * pageSize >= shown.length) listPage = 1; });
  });

  let volume = $derived(inScope.reduce((sum, f) => sum + (f.size_bytes ?? 0), 0));
  let recoverable = $derived(inScope.reduce((sum, f) => sum + (f.dup_bytes ?? 0), 0));
  let sensitive = $derived(inScope.reduce((sum, f) => sum + (f.sensitive_files ?? 0), 0));
  let scored = $derived(inScope.filter((f) => f.score != null));
  let average = $derived(scored.length ? Math.round(scored.reduce((sum, f) => sum + (f.score ?? 0), 0) / scored.length) : null);
  let title = $derived(server ?? (zone ? t('Zone {name}', { name: zone }) : t('All the folders')));

  // ---- selection and actions on several folders (administrators) ----
  let picked = $state(new Set<number>());
  let pickedRows = $derived(shown.filter((f) => picked.has(f.id)));
  let allPicked = $derived(shown.length > 0 && shown.every((f) => picked.has(f.id)));
  function flip(id: number) {
    const next = new Set(picked);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    picked = next;
  }
  const flipAll = () => (picked = allPicked ? new Set() : new Set(shown.map((f) => f.id)));
  let acting = $state(false);
  async function run(kind: 'measure' | 'sensitivity') {
    const ids = pickedRows.map((f) => f.id);
    if (!ids.length || acting) return;
    acting = true;
    try {
      const result = await apiPostData<{ queued?: number[]; failed?: unknown[] }>(fetch, kind === 'measure' ? '/storage-roots/measure' : '/storage-roots/sensitivity-scan', { root_ids: ids });
      const queued = result?.queued?.length ?? 0;
      const failed = result?.failed?.length ?? 0;
      const done = kind === 'measure' ? t('{count} folder(s) queued for a measure.', { count: queued }) : t('{count} folder(s) queued for a sensitivity scan.', { count: queued });
      if (failed) toast.warning(`${done} ${t('{count} refused: see the folder sheet.', { count: failed })}`);
      else toast.success(done);
      picked = new Set();
    } catch (failure) {
      reportUiError(failure, t('The action could not be sent.'), `fives.explore.${kind}`);
    } finally {
      acting = false;
    }
  }
  const exportRows = () =>
    downloadCsv(csvFilename('5s-explorer'), [
      { header: t('Folder'), value: (f: ParkFolder) => f.name },
      { header: t('Path'), value: (f: ParkFolder) => f.path },
      { header: t('Server'), value: (f: ParkFolder) => f.server ?? '' },
      { header: t('Zone'), value: (f: ParkFolder) => f.zone ?? '' },
      { header: t('Volume'), value: (f: ParkFolder) => f.size_bytes ?? '' },
      { header: t('Duplicates'), value: (f: ParkFolder) => f.dup_bytes ?? '' },
      { header: t('Sensitive files'), value: (f: ParkFolder) => f.sensitive_files ?? 0 },
      { header: t('Last measure'), value: (f: ParkFolder) => f.measured_at ?? '' },
      { header: '5S', value: (f: ParkFolder) => f.score ?? '' }
    ], pickedRows.length ? pickedRows : shown);

  // ---- right click ----
  let menu = $state<{ folder: ParkFolder; at: { x: number; y: number } } | null>(null);
  const menuItems = (): ContextMenuItem[] => [
    { key: 'explore', label: t('Explore'), icon: 'bi-columns-gap' },
    { key: 'workshop', label: t('5S workshop'), icon: 'bi-kanban' },
    { key: 'duplicates', label: t('Duplicates'), icon: 'bi-files' },
    { key: 'report', label: t('5S report'), icon: 'bi-file-earmark-bar-graph' },
    { key: 'root', label: t('Open the folder sheet'), icon: 'bi-folder2-open', separated: true }
  ];
  function onPick(key: string) {
    const id = menu?.folder.id;
    if (!id) return;
    if (key === 'explore') void goto(`/five-s/explore/${id}`);
    if (key === 'workshop') void goto(`/five-s/explore/${id}?view=workshop`);
    if (key === 'duplicates') void goto(`/five-s/duplicates/${id}`);
    if (key === 'report') void goto(`/five-s/report/${id}`);
    if (key === 'root') void goto(`/storage-roots?selected=${id}`);
  }
  const openMenu = (folder: ParkFolder) => (event: MouseEvent) => {
    event.preventDefault();
    menu = { folder, at: menuPositionFor(event) };
  };
  const arrow = (key: SortKey) => (sortKey === key ? (sortDesc ? '▾' : '▴') : '');
  const ariaSort = (key: SortKey) => (sortKey === key ? (sortDesc ? 'descending' : 'ascending') : 'none');
</script>

<section class="v2">
  <div class="v2-head">
    <div>
      <h1>{title}</h1>
      <p>{t('Each measured folder, its trend and what there is to gain. Choose a folder, here or in the tree, to see its content.')}</p>
    </div>
    <button type="button" class="b2s-btn b2s-btn-secondary" onclick={exportRows} disabled={!shown.length}><i class="bi bi-download" aria-hidden="true"></i>{t('Export CSV')}</button>
  </div>

  {#if park.loading && !park.folders.length}
    <LoadingState />
  {:else if park.error}
    <InlineAlert tone="warning">{park.error}</InlineAlert>
  {:else}
    <FileSearch onOpen={(hit) => void goto(`/five-s/explore/${hit.storage_root_id}?open=${encodeURIComponent(hit.path.split('\\').slice(0, -1).join('\\'))}&file=${encodeURIComponent(hit.path)}`)} />

    <div class="v2-stats">
      <div class="v2-stat"><i class="bi bi-database" aria-hidden="true"></i><small>{t('Measured volume')}</small><b>{formatBytes(volume)}</b><span>{t('{count} folder(s)', { count: inScope.length })}</span></div>
      <div class="v2-stat"><i class="bi bi-copy is-warn" aria-hidden="true"></i><small>{t('Taken by duplicates')}</small><b>{formatBytes(recoverable)}</b><span>{t('room to win back')}</span></div>
      <div class="v2-stat"><i class="bi bi-shield-exclamation is-bad" aria-hidden="true"></i><small>{t('Sensitive files')}</small><b class:ex-bad={sensitive > 0}>{sensitive}</b><span>{sensitive ? t('to review') : t('nothing to report')}</span></div>
      <div class="v2-stat"><i class="bi bi-stars" aria-hidden="true"></i><small>{t('Average 5S score')}</small><b>{average ?? '—'}</b><span>{t('{count} folder(s) scored', { count: scored.length })}</span></div>
    </div>

    <div class="ex-chips" role="group" aria-label={t('Filters')}>
      {#each CHIPS() as chip (chip.key)}
        <button type="button" class:is-on={chips[chip.key]} aria-pressed={Boolean(chips[chip.key])} onclick={() => (chips = { ...chips, [chip.key]: !chips[chip.key] })}>
          {chip.label}<small>{inScope.filter(chip.test).length}</small></button>
      {/each}
    </div>

    {#if pickedRows.length}
      <div class="v2-bulk" role="region" aria-label={t('Selection')}>
        <b>{t('{count} folder(s) chosen', { count: pickedRows.length })}</b>
        <span>{formatBytes(pickedRows.reduce((sum, f) => sum + (f.size_bytes ?? 0), 0))}</span>
        <span class="ex-bulk-acts">
          {#if isAdmin}
            <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-secondary" disabled={acting} onclick={() => run('measure')}><i class="bi bi-rulers" aria-hidden="true"></i>{t('Measure again')}</button>
            <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-secondary" disabled={acting} onclick={() => run('sensitivity')}><i class="bi bi-shield-lock" aria-hidden="true"></i>{t('Scan for secrets')}</button>
          {/if}
          <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-secondary" onclick={exportRows}><i class="bi bi-download" aria-hidden="true"></i>{t('Export CSV')}</button>
          <button type="button" class="b2s-link-btn" onclick={() => (picked = new Set())}>{t('Clear')}</button>
        </span>
      </div>
    {/if}

    <div class="v2-list ex-list">
      <div class="v2-row is-head ex-grid" role="row">
        <label class="ex-check"><input type="checkbox" checked={allPicked} onchange={flipAll} aria-label={t('Select all ({count})', { count: shown.length })} /></label>
        <span role="columnheader" aria-sort={ariaSort('name')}><button type="button" class="ex-sort" onclick={() => sortBy('name')}>{t('Folder')} {arrow('name')}</button></span>
        <span>{t('Server')}</span>
        <span role="columnheader" aria-sort={ariaSort('size')}><button type="button" class="ex-sort" onclick={() => sortBy('size')}>{t('Volume · last measures')} {arrow('size')}</button></span>
        <span role="columnheader" aria-sort={ariaSort('dup')}><button type="button" class="ex-sort" onclick={() => sortBy('dup')}>{t('Duplicates')} {arrow('dup')}</button></span>
        <span role="columnheader" aria-sort={ariaSort('sensitive')}><button type="button" class="ex-sort" onclick={() => sortBy('sensitive')}>{t('Sensitive')} {arrow('sensitive')}</button></span>
        <span role="columnheader" aria-sort={ariaSort('measured')}><button type="button" class="ex-sort" onclick={() => sortBy('measured')}>{t('Last measure')} {arrow('measured')}</button></span>
        <span role="columnheader" aria-sort={ariaSort('score')}><button type="button" class="ex-sort" onclick={() => sortBy('score')}>5S {arrow('score')}</button></span>
        <span></span>
      </div>
      {#each paged as folder (folder.id)}
        {@const trend = trendOf(folder)}
        <div class="v2-row ex-grid" class:is-picked={picked.has(folder.id)} role="row" tabindex="-1" oncontextmenu={openMenu(folder)}>
          <label class="ex-check"><input type="checkbox" checked={picked.has(folder.id)} onchange={() => flip(folder.id)} aria-label={t('Choose {name}', { name: folder.name })} /></label>
          <div class="v2-nm"><a href={`/five-s/explore/${folder.id}`}>{folder.name}</a><small title={folder.path}>{folder.path}</small></div>
          <div class="v2-nm"><span>{folder.server ?? '—'}</span><span class="v2-sub">{folder.zone ?? '—'}</span></div>
          <div class="ex-vol"><span>{folder.size_bytes != null ? formatBytes(folder.size_bytes) : '—'}</span>
            {#if trend.length > 1}<Sparkline points={trend} width={140} height={24} title={t('{count} measures: {from} → {to}', { count: trend.length, from: formatBytes(trend[0]), to: formatBytes(trend[trend.length - 1]) })} />{/if}</div>
          <span class="ex-num">{folder.dup_bytes == null ? '—' : folder.dup_bytes ? formatBytes(folder.dup_bytes) : t('none')}</span>
          <span>{#if folder.sensitive_files}<span class="v2-tag is-bad">{t('{count} file(s)', { count: folder.sensitive_files })}</span>{:else}<span class="ex-mut">{t('none')}</span>{/if}</span>
          <span class="ex-when" title={folder.measured_at ? formatDate(folder.measured_at) : ''}>{folder.measured_at ? timeAgo(folder.measured_at) : t('never')}</span>
          <span class={`v2-tag is-${toneOf(folder.score)}`}>{folder.score ?? '—'}</span>
          <button type="button" class="v2-dots" aria-label={t('Actions on {name}', { name: folder.name })} title={t('Actions on {name}', { name: folder.name })} onclick={openMenu(folder)}><i class="bi bi-three-dots" aria-hidden="true"></i></button>
        </div>
      {:else}
        <div class="v2-empty">{inScope.length ? t('No folder matches these filters.') : t('No measured folder here yet.')}</div>
      {/each}
    </div>
    {#if shown.length > pageSize}<Pagination total={shown.length} bind:page={listPage} bind:pageSize pageSizes={[50, 100, 200]} />{/if}
    <p class="ex-hint">{t('Right click on a folder: its 5S workshop, duplicates, report and sheet.')}</p>
  {/if}
</section>

<ContextMenu open={menu != null} title={menu?.folder.name ?? ''} subtitle={menu?.folder.path ?? ''} items={menuItems()} at={menu?.at}
  onClose={() => (menu = null)} {onPick} />

<style>
  /* Folder and server narrower, the volume and its last measures wider */
  .ex-grid { grid-template-columns: 36px minmax(170px, 1.3fr) minmax(100px, 0.7fr) minmax(240px, 1.4fr) 110px 110px 120px 56px 36px; min-width: 1040px; }
  .ex-list { overflow-x: auto; }
  .ex-check { display: flex; align-items: center; justify-content: center; cursor: pointer; }
  .ex-check input { width: 16px; height: 16px; accent-color: var(--b2s-accent); }
  .ex-sort { padding: 0; border: 0; background: none; font: inherit; color: inherit; text-align: left; cursor: pointer; }
  .ex-vol { display: flex; align-items: center; gap: 10px; font-size: 13px; font-weight: 500; }
  .ex-vol > span { width: 64px; }
  .ex-num, .ex-when { font-size: 13px; }
  .ex-mut { color: var(--b2s-color-text-muted); font-size: 13px; }
  .ex-bad { color: var(--b2s-color-danger-strong); }
  .ex-hint { margin: 0; color: var(--b2s-color-text-muted); font-size: 12px; }
  .ex-chips { display: flex; flex-wrap: wrap; gap: 8px; }
  .ex-chips button { display: inline-flex; gap: 6px; align-items: center; height: 32px; padding: 0 12px; border: 1px solid var(--b2s-color-border); border-radius: 999px;
    background: var(--b2s-color-surface, #fff); font: inherit; font-size: 13px; color: var(--b2s-color-text); cursor: pointer; }
  .ex-chips button small { color: var(--b2s-color-text-muted); font-size: 12px; }
  .ex-chips button.is-on { border-color: var(--b2s-accent); background: var(--b2s-accent); color: #fff; }
  .ex-chips button.is-on small { color: var(--b2s-color-border-strong); }
  .ex-bulk-acts { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-left: auto; }
  .is-picked { background: var(--b2s-color-surface-muted); }
</style>
