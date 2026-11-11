<script context="module" lang="ts">
  // Kept across visits: coming back from a folder returns to the same filter, zone and sort
  const memory = { filter: 'all' as Filter, zone: '', sort: 'state' as SortKey, desc: false };
  type Filter = 'all' | 'review' | 'no-guardian' | 'ending' | 'blocking';
  type SortKey = 'name' | 'server' | 'people' | 'guardians' | 'quota' | 'state';
</script>

<script lang="ts">
  import { page as pageStore } from '$app/stores';
  import { pulseOnIncrease } from '$lib/utils/motion';
  import { invalidate } from '$app/navigation';
  import { t } from '$lib/i18n';
  import { formatBytes, timeAgo } from '$lib/utils/format';
  import { apiGetData, apiPostData } from '$lib/api/client';
  import { reportUiError } from '$lib/errors';
  import { toast } from '$lib/stores/toast';
  import AppModal from '$lib/components/ui/AppModal.svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import EntityActionButton from '$lib/components/entity/EntityActionButton.svelte';
  import GovernancePicker from '$lib/components/storage-roots/GovernancePicker.svelte';
  import StorageRootContextMenu from '$lib/components/storage-roots/StorageRootContextMenu.svelte';
  import type { FolderActionKind } from '$lib/components/storage-roots/StorageRootFolderActions.svelte';
  import type { StorageRootRow } from '$lib/utils/storage-roots';
  import { matchesFolderQuery, parseFolderQuery } from '$lib/components/storage-roots/folder-query';
  import FolderQueryAssist from '$lib/components/storage-roots/FolderQueryAssist.svelte';
  import { accessRequestAccessLabel } from '$lib/mappers/access-requests.mapper';

  type Alert = { count: number; tone: 'warning' | 'error'; label?: string } | null;
  type Tone = 'ok' | 'warn' | 'bad' | 'read';
  type Grants = { read: number; write: number; ending: number };
  type Line = {
    row: StorageRootRow;
    id: number;
    name: string;
    path: string;
    dfsPath: string;
    server: string;
    zone: string;
    zoneKey: string;
    grants: Grants;
    guardians: number;
    noGuardian: boolean;
    pending: number;
    alerts: number;
    blocking: boolean;
    review: boolean;
    tone: Tone;
    label: string;
    readAt: string;
  };
  type Failure = { name: string; message: string };

  /**
   * Home of the folders: one compact table made for hundreds of folders, with counters that filter,
   * sorting, and (administrators) actions on a selection: guardians, tags, ACL read, export.
   */
  export let rows: StorageRootRow[] = [];
  export let accessRequests: any[] = [];
  export let tags: Array<Record<string, any>> = [];
  export let query = '';
  export let isAdmin = false;
  export let initialFilter: string | null = null;
  /** Zone id from the link of a zone page (?zone=) */
  export let initialZone: string | null = null;
  /** File server id from the link of a server page (?endpoint=): only its folders */
  export let initialEndpoint: string | null = null;
  /** ?bulk=guardians: the folders shown are selected and the guardians dialog opens at once */
  export let initialBulk: string | null = null;
  export let rootAlertSummary: (row: StorageRootRow) => Alert = () => null;
  export let onQueryChange: (value: string) => void = () => {};
  export let onOpenRoot: (id: number) => void = () => {};
  export let onAdd: (() => void) | null = null;
  export let onFolderAction: ((kind: FolderActionKind, row: StorageRootRow) => void) | null = null;

  const PAGE = 50;
  const BATCH = 25;
  const DAY = 86_400_000;

  let filter: Filter = (['all', 'review', 'no-guardian', 'ending', 'blocking'] as const).includes(initialFilter as Filter)
    ? (initialFilter as Filter)
    : memory.filter;
  let zoneFilter = initialZone || memory.zone;
  let sortKey: SortKey = memory.sort;
  let desc = memory.desc;
  let shown = PAGE;
  let checked = new Set<number>();
  let menuRow: StorageRootRow | null = null;
  let menuAt = { x: 0, y: 0 };

  $: memory.filter = filter;
  $: memory.zone = zoneFilter;
  $: memory.sort = sortKey;
  $: memory.desc = desc;

  // Accesses granted through requests and still running (an NTFS entry set by hand is not counted)
  function grantsByRoot(list: any[]): Map<number, Grants> {
    const now = Date.now();
    const map = new Map<number, Grants>();
    for (const request of list) {
      if (!['executed', 'approved', 'enforced', 'applied'].includes(String(request?.status ?? '').trim().toLowerCase())) continue;
      const id = Number(request?.storage_root_id ?? request?.target_id ?? 0);
      const ends = new Date(String(request?.expires_at ?? '')).getTime() || 0;
      if (!(id > 0) || (ends && ends <= now)) continue;
      const label = accessRequestAccessLabel(request).toLowerCase();
      const entry = map.get(id) ?? { read: 0, write: 0, ending: 0 };
      if (label.includes('write') || label.includes('écriture') || label.includes('modif') || label.includes('contrib')) entry.write += 1;
      else entry.read += 1;
      if (ends && ends - now <= 30 * DAY) entry.ending += 1;
      map.set(id, entry);
    }
    return map;
  }

  function lineOf(row: StorageRootRow, grants: Map<number, Grants>): Line {
    const id = Number(row?.storage_root_id ?? (row as any)?.id ?? 0);
    const alert = rootAlertSummary(row);
    const alerts = alert?.count ?? 0;
    const pending = Number((row as any)?.pending_validation_count ?? 0);
    const blocking = alerts > 0 && alert?.tone === 'error';
    const noGuardian = String((row as any)?.open_alert_types ?? '').includes('missing_guardian');
    const path = String(row?.root_path ?? (row as any)?.normalized_root_path ?? '').trim();
    const state: Pick<Line, 'tone' | 'label' | 'review'> = blocking
      ? { tone: 'bad', label: alert?.label || t('{count} alert(s)', { count: alerts }), review: true }
      : pending > 0
        ? { tone: 'warn', label: t('{count} pending requests', { count: pending }), review: true }
        : alerts > 0
          ? { tone: 'read', label: t('{count} alert(s)', { count: alerts }), review: true }
          : { tone: 'ok', label: t('Nothing to do'), review: false };
    return {
      row,
      id,
      name: String(row?.storage_root_name ?? row?.storage_root_code ?? t('Storage root')).trim() || t('Storage root'),
      path,
      dfsPath: String((row as any)?.dfs_path ?? '').trim(),
      server: String((row as any)?.storage_endpoint_name ?? '').trim() || path.split(/[\\/]+/).filter(Boolean)[0] || t('Unknown server'),
      zone: String(row?.zone_name ?? t('Unassigned zone')).trim() || t('Unassigned zone'),
      zoneKey: String(row?.zone_id ?? ''),
      grants: grants.get(id) ?? { read: 0, write: 0, ending: 0 },
      guardians: Number((row as any)?.guardians_count ?? 0),
      noGuardian,
      pending,
      alerts,
      blocking,
      ...state,
      readAt: String((row as any)?.last_scan_at ?? (row as any)?.last_probe_at ?? '')
    };
  }

  $: grants = grantsByRoot(accessRequests);
  $: lines = rows.map((row) => lineOf(row, grants)).filter((line) => line.id > 0);
  $: zones = [...new Map(lines.map((line) => [line.zoneKey, line.zone])).entries()].sort((a, b) => a[1].localeCompare(b[1], 'fr'));
  $: if (zoneFilter && !zones.some(([key]) => key === zoneFilter)) zoneFilter = '';
  let endpointFilter = Number(initialEndpoint ?? 0) || 0;
  $: endpointName = endpointFilter ? lines.find((line) => Number((line.row as any)?.storage_endpoint_id ?? 0) === endpointFilter)?.server ?? '' : '';
  $: zoned = (zoneFilter ? lines.filter((line) => line.zoneKey === zoneFilter) : lines).filter(
    (line) => !endpointFilter || Number((line.row as any)?.storage_endpoint_id ?? 0) === endpointFilter
  );

  const PASSES: Record<Filter, (line: Line) => boolean> = {
    all: () => true,
    review: (line) => line.review,
    'no-guardian': (line) => line.noGuardian,
    ending: (line) => line.grants.ending > 0,
    blocking: (line) => line.blocking
  };
  $: counters = [
    { key: 'all' as Filter, label: t('Folders') },
    { key: 'review' as Filter, label: t('To review') },
    { key: 'no-guardian' as Filter, label: t('Without enough guardians') },
    { key: 'ending' as Filter, label: t('Ending within 30 days') },
    { key: 'blocking' as Filter, label: t('Blocking') }
  ].map((counter) => ({ ...counter, count: zoned.filter(PASSES[counter.key]).length }));

  // Express search: « tag:… gardien:… est:… » filter, the rest of the text is searched
  $: parsed = parseFolderQuery(query);
  $: needle = parsed.text.trim().toLowerCase();
  let searchFocused = false;
  const haystack = (line: Line) =>
    [line.name, line.path, line.dfsPath, line.server, line.zone, ...(Array.isArray(line.row?.tags) ? line.row.tags.map((tag: any) => tag?.label ?? tag?.name ?? '') : [])]
      .join(' ')
      .toLowerCase();
  const people = (line: Line) => line.grants.read + line.grants.write;
  const SORTS: Record<SortKey, (a: Line, b: Line) => number> = {
    name: (a, b) => a.name.localeCompare(b.name, 'fr', { numeric: true, sensitivity: 'base' }),
    server: (a, b) => a.server.localeCompare(b.server, 'fr') || SORTS.name(a, b),
    people: (a, b) => people(b) - people(a) || SORTS.name(a, b),
    guardians: (a, b) => a.guardians - b.guardians || SORTS.name(a, b),
    // The fullest first; folders without quota last
    quota: (a, b) => Number(b.row?.quota_used_percent ?? -1) - Number(a.row?.quota_used_percent ?? -1) || SORTS.name(a, b),
    state: (a, b) => Number(b.blocking) - Number(a.blocking) || Number(b.review) - Number(a.review) || b.pending - a.pending || SORTS.name(a, b)
  };
  $: visible = zoned
    .filter(PASSES[filter])
    .filter((line) => !needle || haystack(line).includes(needle))
    .filter((line) => matchesFolderQuery(line.row, parsed.filters))
    .sort((a, b) => (desc ? -1 : 1) * SORTS[sortKey](a, b));
  $: page = visible.slice(0, shown);

  function setFilter(next: Filter) {
    filter = next;
    shown = PAGE;
  }

  function sortBy(key: SortKey) {
    if (sortKey === key) desc = !desc;
    else {
      sortKey = key;
      desc = false;
    }
  }
  const sortMark = (key: SortKey, current: SortKey, reversed: boolean) => (key === current ? (reversed ? ' ↑' : ' ↓') : '');

  // Selection (administrators): kept while filtering, cleared after an action
  $: checkedLines = lines.filter((line) => checked.has(line.id));
  $: allVisibleChecked = visible.length > 0 && visible.every((line) => checked.has(line.id));
  function toggle(id: number) {
    if (checked.has(id)) checked.delete(id);
    else checked.add(id);
    checked = checked;
  }
  function toggleAll() {
    const check = !allVisibleChecked;
    for (const line of visible) {
      if (check) checked.add(line.id);
      else checked.delete(line.id);
    }
    checked = checked;
  }

  function openMenu(line: Line, event: MouseEvent) {
    event.preventDefault();
    menuRow = line.row;
    menuAt = { x: event.clientX, y: event.clientY };
  }

  // ---- Bulk actions --------------------------------------------------------
  let action: 'guardians' | 'tags' | 'check' | 'sensitivity' | 'measure' | null = null;
  // Beyond 50 folders, an action on the selection is confirmed explicitly
  const BULK_CONFIRM_FROM = 50;
  let bulkConfirmed = false;
  $: if (action === null) bulkConfirmed = false;
  let running = false;
  let failures: Failure[] = [];
  let peopleOptions: { id: number; label: string; hint?: string }[] = [];
  let peopleLoaded = false;
  let guardianIds: number[] = [];
  let tagIds = new Set<number>();

  let bulkStarted = false;
  // ?bulk=select&ids=1,2,3: the folders chosen in the tree, ready for an action (guardians, tags, ACL, export)
  $: if (!bulkStarted && isAdmin && initialBulk === 'select' && visible.length) {
    bulkStarted = true;
    const ids = new Set(String($pageStore.url.searchParams.get('ids') ?? '').split(',').map(Number).filter((id) => id > 0));
    checked = new Set(visible.map((line) => line.id).filter((id) => ids.has(id)));
  }
  $: if (!bulkStarted && isAdmin && initialBulk === 'guardians' && visible.length) {
    bulkStarted = true;
    checked = new Set(visible.map((line) => line.id));
    void openAction('guardians');
  }

  async function openAction(kind: Exclude<typeof action, null>) {
    failures = [];
    action = kind;
    if (kind === 'guardians' && !peopleLoaded) {
      try {
        const identity = await apiGetData<{ users?: any[]; items?: any[] }>(fetch, '/identity');
        const list = identity?.users ?? (identity?.items ?? []).filter((row: any) => row?.type !== 'group');
        peopleOptions = list
          .filter((row: any) => String(row?.status ?? 'active').toLowerCase() !== 'inactive')
          .map((row: any) => ({ id: Number(row.id), label: String(row.display_name || row.username || row.id), hint: String(row.email || row.username || '') }));
        peopleLoaded = true;
      } catch (error) {
        reportUiError(error, t('Unable to load the people of the directory.'), 'storage-roots.bulk.people');
      }
    }
  }

  function closeAction() {
    if (running) return;
    action = null;
    guardianIds = [];
    tagIds = new Set();
  }

  const nameOf = (id: number) => lines.find((line) => line.id === id)?.name ?? String(id);

  async function inBatches(path: string, body: (ids: number[]) => Record<string, unknown>, okKey: 'updated' | 'queued') {
    const ids = [...checked];
    let ok = 0;
    const failed: Failure[] = [];
    for (let start = 0; start < ids.length; start += BATCH) {
      const answer = await apiPostData<Record<string, any>>(fetch, path, body(ids.slice(start, start + BATCH)));
      const done: number[] = answer?.[okKey] ?? [];
      ok += done.length;
      for (const id of done) checked.delete(id);
      failed.push(...(answer?.failed ?? []).map((row: any) => ({ name: nameOf(Number(row.storage_root_id)), message: t(String(row.message ?? '')) })));
    }
    checked = checked;
    return { ok, failed };
  }

  async function runAction() {
    if (!action || running) return;
    running = true;
    try {
      const result =
        action === 'guardians'
          ? await inBatches('/storage-roots/bulk-guardians', (ids) => ({ root_ids: ids, guardian_ids: guardianIds }), 'updated')
          : action === 'tags'
            ? await inBatches('/storage-roots/bulk-tags', (ids) => ({ root_ids: ids, tag_ids: [...tagIds] }), 'updated')
            : action === 'sensitivity'
              ? await inBatches('/storage-roots/sensitivity-scan', (ids) => ({ root_ids: ids }), 'queued')
              : action === 'measure'
                ? await inBatches('/storage-roots/measure', (ids) => ({ root_ids: ids }), 'queued')
                : await inBatches('/storage-roots/bulk-check', (ids) => ({ root_ids: ids }), 'queued');
      failures = result.failed;
      if (result.ok) {
        toast.success(
          action === 'check'
            ? t('{count} folder(s) queued for a test and an ACL read.', { count: result.ok })
            : action === 'sensitivity'
              ? t('{count} folder(s) queued for a sensitivity scan.', { count: result.ok })
            : action === 'measure'
              ? t('{count} folder(s) queued for a measure.', { count: result.ok })
            : t('{count} folder(s) updated.', { count: result.ok })
        );
      }
      if (!result.failed.length) {
        running = false;
        closeAction();
      }
      await invalidate('app:storage-roots');
    } catch (error) {
      reportUiError(error, t('The action failed.'), `storage-roots.bulk.${action}`);
    } finally {
      running = false;
    }
  }

  // ---- Export (the selection, or what is shown) ---------------------------
  function exportCsv() {
    const source = checkedLines.length ? checkedLines : visible;
    const cell = (value: unknown) => `"${String(value ?? '').replace(/"/g, '""')}"`;
    const header = [t('Folder'), t('Path'), t('DFS path'), t('Zone'), t('Server'), t('Read'), t('Modify'), t('Guardians'), t('State')];
    const body = source.map((line) =>
      [line.name, line.path, line.dfsPath, line.zone, line.server, line.grants.read, line.grants.write, line.guardians, line.label].map(cell).join(';')
    );
    const blob = new Blob([`﻿${[header.map(cell).join(';'), ...body].join('\r\n')}`], { type: 'text/csv;charset=utf-8' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `borntoshare-dossiers-${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  }
</script>

<div class="tb">
  <header class="sg-head">
    <div class="sg-title">
      <h1>{t('Folders')}</h1>
      <p>{t('{folders} folders · {count} to review', { folders: zoned.length, count: counters[1].count })}</p>
    </div>
    <div class="sg-search-wrap">
      <label class="sg-search">
        <i class="bi bi-search" aria-hidden="true"></i>
        <input type="search" aria-label={t('Search all folders')} placeholder={t('Search, or tag:… gardien:… est:…')} value={query}
          on:focus={() => (searchFocused = true)} on:blur={() => (searchFocused = false)}
          on:input={(event) => { onQueryChange(event.currentTarget.value); shown = PAGE; }} />
      </label>
      <FolderQueryAssist floating focused={searchFocused} {query} rows={zoned.map((line) => line.row)}
        tags={tags.map((tag) => String(tag?.label ?? tag?.name ?? '')).filter(Boolean)}
        onQueryChange={(value) => { onQueryChange(value); shown = PAGE; }} />
    </div>
    {#if endpointFilter}
      <button type="button" class="b2s-btn b2s-btn-secondary tb__scope" on:click={() => (endpointFilter = 0)} title={t('Show the folders of every server')}>
        <i class="bi bi-hdd-network" aria-hidden="true"></i>{endpointName || t('Server')}<i class="bi bi-x" aria-hidden="true"></i>
      </button>
    {/if}
    {#if zones.length > 1}
      <select class="b2s-input tb__zone" aria-label={t('Filter by zone')} bind:value={zoneFilter}>
        <option value="">{t('All zones')}</option>
        {#each zones as [key, label] (key)}<option value={key}>{label}</option>{/each}
      </select>
    {/if}
    <button type="button" class="b2s-btn b2s-btn-secondary" on:click={exportCsv} disabled={!visible.length}>
      <i class="bi bi-download" aria-hidden="true"></i>{t('Export')}
    </button>
    {#if onAdd}
      <button type="button" class="b2s-btn b2s-btn-primary" on:click={onAdd}><i class="bi bi-plus-lg" aria-hidden="true"></i>{t('Add folders')}</button>
    {/if}
  </header>

  <div class="tb__counters" role="group" aria-label={t('Filters')}>
    {#each counters as counter (counter.key)}
      <button type="button" class:on={filter === counter.key} aria-pressed={filter === counter.key} on:click={() => setFilter(counter.key)}>
        <span>{counter.label}</span>
        <b class:warn={counter.key !== 'all' && counter.count > 0} class:bad={counter.key === 'blocking' && counter.count > 0} use:pulseOnIncrease={counter.count}>{counter.count}</b>
      </button>
    {/each}
  </div>

  <div class="tb__grid" class:admin={isAdmin}>
    <div class="tb__head">
      {#if isAdmin}<span><input type="checkbox" checked={allVisibleChecked} on:change={toggleAll} aria-label={t('Select the folders shown')} /></span>{/if}
      <button type="button" on:click={() => sortBy('name')}>{t('Folder')}{sortMark('name', sortKey, desc)}</button>
      <button type="button" on:click={() => sortBy('server')}>{t('Server')}{sortMark('server', sortKey, desc)}</button>
      <button type="button" on:click={() => sortBy('people')}>{t('People')}{sortMark('people', sortKey, desc)}</button>
      <button type="button" on:click={() => sortBy('guardians')}>{t('Guardians')}{sortMark('guardians', sortKey, desc)}</button>
      <button type="button" on:click={() => sortBy('quota')}>{t('Quota')}{sortMark('quota', sortKey, desc)}</button>
      <button type="button" on:click={() => sortBy('state')}>{t('State')}{sortMark('state', sortKey, desc)}</button>
      <span>{t('ACL read')}</span>
    </div>
    {#each page as line (line.id)}
      <div class="tb__row" class:sel={checked.has(line.id)} on:contextmenu={(event) => openMenu(line, event)}>
        {#if isAdmin}<span><input type="checkbox" checked={checked.has(line.id)} on:change={() => toggle(line.id)} aria-label={t('Select {name}', { name: line.name })} /></span>{/if}
        <button type="button" class="tb__name" on:click={() => onOpenRoot(line.id)}>
          <strong>{line.name}{#if Number(line.row?.password_files ?? 0) > 0}<span class="tb__sens" title={t('{count} file(s) holding passwords', { count: Number(line.row?.password_files) })}><i class="bi bi-key" aria-hidden="true"></i>{t('passwords')}</span>{:else if Number(line.row?.sensitive_files ?? 0) > 0}<span class="tb__sens" title={t('{count} sensitive file(s) found by the last scan', { count: Number(line.row?.sensitive_files) })}><i class="bi bi-shield-lock" aria-hidden="true"></i>{t('sensitive')}</span>{/if}</strong>
          <small title={line.dfsPath || line.path}>{line.dfsPath || line.path}</small>
        </button>
        <span class="tb__server"><span>{line.server}</span><small>{line.zone}</small></span>
        <span class="tb__people">
          {#if people(line)}
            <b>{people(line)}</b>
            <span class="tb__split" title={t('{read} read · {write} modify', { read: line.grants.read, write: line.grants.write })}>
              <i class="read" style={`flex:${line.grants.read}`}></i><i class="write" style={`flex:${line.grants.write}`}></i>
            </span>
          {:else}<span class="muted">—</span>{/if}
        </span>
        <span>
          {#if line.noGuardian}<span class="sg-tag warn">{line.guardians ? t('{count} of too few', { count: line.guardians }) : t('None')}</span>
          {:else}<span class="sg-tag">{t('{count} guardian(s)', { count: line.guardians })}</span>{/if}
        </span>
        <span class="tb__quota">
          {#if line.row?.quota_limit_bytes != null}
            {@const pct = line.row?.quota_used_percent == null ? null : Number(line.row.quota_used_percent)}
            <span class="tb__qbar" data-tone={pct == null ? 'neutral' : pct >= 100 ? 'danger' : pct >= Number(line.row?.quota_warn_percent ?? 85) ? 'warning' : 'ok'}
              title={t('{used} of {limit}', { used: formatBytes(line.row?.quota_used_bytes), limit: formatBytes(line.row?.quota_limit_bytes) })}>
              <i style={`width:${Math.min(100, pct ?? 0)}%`}></i></span>
            <small>{pct == null ? formatBytes(line.row?.quota_limit_bytes) : `${Math.round(pct)} %`}{#if Number(line.row?.quota_pending_requests ?? 0) > 0} <i class="bi bi-arrow-up-circle" title={t('Request for more room waiting')}></i>{/if}</small>
          {:else}<span class="muted">—</span>{/if}
        </span>
        <span><span class={`sg-tag ${line.tone}`}>{line.label}</span></span>
        <span class="muted">{line.readAt ? timeAgo(line.readAt) : t('never')}</span>
      </div>
    {:else}
      <p class="tb__empty">{needle ? t('No folder matches your search.') : t('No folder in this view.')}</p>
    {/each}
    <footer class="tb__foot">
      <span>{t('{shown} of {total} folder(s)', { shown: page.length, total: visible.length })}</span>
      {#if page.length < visible.length}
        <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-secondary" on:click={() => (shown += PAGE)}>
          {t('Show {count} more', { count: Math.min(PAGE, visible.length - page.length) })}
        </button>
      {/if}
    </footer>
  </div>

  {#if isAdmin && checked.size}
    <div class="tb__bulk" role="region" aria-label={t('Selection')}>
      <b>{t('{count} folder(s) selected', { count: checked.size })}</b>
      <button type="button" class="b2s-btn b2s-btn-sm" on:click={() => openAction('guardians')}>{t('Add guardians')}</button>
      <button type="button" class="b2s-btn b2s-btn-sm" on:click={() => openAction('tags')}>{t('Add tags')}</button>
      <button type="button" class="b2s-btn b2s-btn-sm" on:click={() => openAction('check')}>{t('Read the ACLs')}</button>
      <button type="button" class="b2s-btn b2s-btn-sm" on:click={() => openAction('sensitivity')}>{t('Scan for secrets')}</button>
      <button type="button" class="b2s-btn b2s-btn-sm" on:click={() => openAction('measure')}>{t('Measure')}</button>
      <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-primary" on:click={exportCsv}>{t('Export')}</button>
      <button type="button" class="b2s-btn b2s-btn-sm tb__clear" on:click={() => (checked = new Set())}>{t('Clear the selection')}</button>
    </div>
  {/if}
</div>

<AppModal
  open={action !== null}
  onClose={closeAction}
  title={action === 'guardians' ? t('Add guardians') : action === 'tags' ? t('Add tags') : action === 'sensitivity' ? t('Scan for secrets') : action === 'measure' ? t('Measure the folders') : t('Read the ACLs')}
  subtitle={t('{count} folder(s) selected', { count: checked.size })}
  iconClass={action === 'guardians' ? 'bi bi-person-check' : action === 'tags' ? 'bi bi-tags' : action === 'sensitivity' ? 'bi bi-shield-lock' : action === 'measure' ? 'bi bi-rulers' : 'bi bi-arrow-clockwise'}
>
  {#if action === 'guardians'}
    <GovernancePicker id="bulk-guardians" label={t('Guardians')} placeholder={t('Search a person…')} options={peopleOptions} bind:selected={guardianIds} />
    <p class="muted">{t('The folders keep the guardians they already have.')}</p>
  {:else if action === 'tags'}
    {#if tags.length}
      <div class="tb__tags">
        {#each tags as tag (tag.id)}
          <label class="tb__tag">
            <input type="checkbox" checked={tagIds.has(Number(tag.id))}
              on:change={() => { if (tagIds.has(Number(tag.id))) tagIds.delete(Number(tag.id)); else tagIds.add(Number(tag.id)); tagIds = tagIds; }} />
            {tag.label ?? tag.name ?? tag.code}
          </label>
        {/each}
      </div>
      <p class="muted">{t('The folders keep the tags they already have.')}</p>
    {:else}
      <InlineAlert tone="info">{t('No tag yet: create one in Tags first.')}</InlineAlert>
    {/if}
  {:else if action === 'check'}
    <p>{t('The worker tests each folder and reads its NTFS permissions. The results appear on each folder in the next minutes.')}</p>
  {:else if action === 'sensitivity'}
    <p>{t('The worker looks in each folder for passwords, keys and password vaults (read only; the secrets are never kept). The results appear on each folder, and the policies about sensitivity apply at once.')}</p>
  {:else if action === 'measure'}
    <p>{t('The worker walks through each folder (read only): size, number of files, age of the data, clutter and duplicates. The results appear on each folder.')}</p>
  {/if}
  {#if checked.size > BULK_CONFIRM_FROM}
    <label class="tb__confirm"><input type="checkbox" bind:checked={bulkConfirmed} />{t('I confirm the action on {count} folders', { count: checked.size })}</label>
  {/if}
  {#if failures.length}
    <InlineAlert tone="warning">
      {t('{count} folder(s) not updated:', { count: failures.length })}
      <ul class="tb__failures">{#each failures.slice(0, 8) as failure}<li><strong>{failure.name}</strong> — {failure.message}</li>{/each}</ul>
    </InlineAlert>
  {/if}
  <svelte:fragment slot="footer">
    <EntityActionButton variant="secondary" label={t('Cancel')} onClick={closeAction} />
    <EntityActionButton
      variant="primary"
      busy={running}
      disabled={(action === 'guardians' && !guardianIds.length) || (action === 'tags' && !tagIds.size) || !checked.size || (checked.size > BULK_CONFIRM_FROM && !bulkConfirmed)}
      label={action === 'check' ? t('Start the reads') : action === 'sensitivity' ? t('Start the scans') : action === 'measure' ? t('Start the measures') : t('Apply')}
      onClick={runAction}
    />
  </svelte:fragment>
</AppModal>

<StorageRootContextMenu
  row={menuRow}
  at={menuAt}
  onClose={() => (menuRow = null)}
  onOpen={(row) => onOpenRoot(Number(row?.storage_root_id ?? 0))}
  onAction={(kind, row) => onFolderAction?.(kind, row)}
  canManage={Boolean(onFolderAction)}
/>

<style>
  .tb { display: flex; flex-direction: column; gap: 16px; padding: 24px 28px 36px; }
  .tb__zone { width: auto; max-width: 220px; }
  .tb__counters { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; }
  .tb__counters button { display: flex; flex-direction: column; align-items: flex-start; gap: 2px; padding: 10px 14px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); text-align: left; cursor: pointer; }
  .tb__counters button.on { border-color: var(--b2s-color-text); box-shadow: inset 0 0 0 1px var(--b2s-color-text); }
  .tb__counters span { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .tb__counters b { font-size: 22px; font-weight: 600; line-height: 1.2; }
  .tb__counters b.warn { color: var(--b2s-color-warning-strong); }
  .tb__counters b.bad { color: var(--b2s-color-danger-strong); }
  .tb__grid { border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); overflow: hidden; }
  .tb__head, .tb__row { display: grid; grid-template-columns: minmax(0, 1.7fr) minmax(0, 0.9fr) 120px 140px 96px 190px 110px; gap: 12px; align-items: center; padding: 0 14px; }
  .admin .tb__head, .admin .tb__row { grid-template-columns: 24px minmax(0, 1.7fr) minmax(0, 0.9fr) 120px 140px 96px 190px 110px; }
  .tb__quota { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
  .tb__quota small { color: var(--b2s-color-text-muted); font-size: var(--b2s-font-micro); font-variant-numeric: tabular-nums; }
  .tb__qbar { position: relative; display: block; height: 6px; border-radius: var(--b2s-radius-pill); background: var(--b2s-color-neutral-soft); overflow: hidden; --tb-fill: var(--b2s-color-info-strong); }
  .tb__qbar[data-tone='ok'] { --tb-fill: var(--b2s-color-success-strong, #1a7f37); }
  .tb__qbar[data-tone='warning'] { --tb-fill: var(--b2s-color-warning-strong, #9a5b00); }
  .tb__qbar[data-tone='danger'] { --tb-fill: var(--b2s-color-danger-strong, #b42318); }
  .tb__qbar i { position: absolute; inset: 0 auto 0 0; background: var(--tb-fill); border-radius: inherit; }
  .tb__head { position: sticky; top: 0; z-index: 1; min-height: 40px; background: var(--b2s-color-surface-soft, #f6f7f9); border-bottom: 1px solid var(--b2s-color-border); font-size: var(--b2s-fs-xs); color: var(--b2s-color-text-muted); }
  .tb__head button { padding: 0; border: 0; background: none; color: inherit; font: inherit; font-weight: 500; text-align: left; cursor: pointer; }
  .tb__row { min-height: 52px; border-top: 1px solid var(--b2s-color-border); }
  .tb__head + .tb__row { border-top: 0; }
  .tb__row:hover { background: var(--b2s-color-surface-soft, #f6f7f9); }
  .tb__row.sel { background: var(--b2s-accent-soft); }
  .tb__name { display: flex; flex-direction: column; min-width: 0; padding: 6px 0; border: 0; background: none; color: inherit; font: inherit; text-align: left; cursor: pointer; }
  .tb__name strong { font-weight: 500; }
  .tb__name:hover strong { text-decoration: underline; }
  .tb__name small, .tb__server small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .tb__name small { font-family: var(--b2s-font-mono); }
  .tb__server { display: flex; flex-direction: column; min-width: 0; font-size: var(--b2s-fs-sm); }
  .tb__server span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .tb__people { display: flex; align-items: center; gap: 8px; }
  .tb__split { display: flex; gap: 2px; width: 50px; height: 6px; }
  .tb__split i { display: block; min-width: 0; border-radius: 3px; }
  .tb__split i.read { background: var(--b2s-color-info); }
  .tb__split i.write { background: var(--b2s-color-warning); }
  .muted { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .tb__empty { margin: 0; padding: 28px; text-align: center; color: var(--b2s-color-text-muted); }
  .tb__foot { display: flex; align-items: center; gap: 10px; padding: 10px 14px; border-top: 1px solid var(--b2s-color-border); font-size: var(--b2s-fs-sm); color: var(--b2s-color-text-muted); }
  .tb__foot span { margin-right: auto; }
  .tb__bulk { position: sticky; bottom: 16px; z-index: 5; display: flex; flex-wrap: wrap; align-items: center; gap: 10px; padding: 10px 14px; border-radius: var(--b2s-radius-md); background: var(--b2s-topbar-bg, #0e1218); color: #fff; box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2); }
  .tb__bulk .b2s-btn:not(.b2s-btn-primary) { background: transparent; color: #fff; border: 1px solid rgba(255, 255, 255, 0.25); }
  .tb__clear { margin-left: auto; }
  .tb__tags { display: flex; flex-wrap: wrap; gap: 8px; }
  .tb__tag { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-pill); cursor: pointer; }
  .tb__failures { margin: 6px 0 0; padding-left: 18px; }
  .sg-search-wrap { position: relative; flex: 0 1 420px; display: flex; flex-direction: column; }
  .sg-search-wrap .sg-search { flex: 1 1 auto; }
  .tb__sens { display: inline-flex; align-items: center; gap: 4px; margin-left: 8px; padding: 1px 8px; border-radius: var(--b2s-radius-pill); background: var(--b2s-color-danger-soft, #fdecea); color: var(--b2s-color-danger-strong, #b42318); font-size: var(--b2s-font-micro); font-weight: 600; vertical-align: middle; }
  .tb__confirm { display: flex; gap: 8px; align-items: center; margin-top: 10px; padding: 10px 12px; border-radius: var(--b2s-radius-md); background: var(--b2s-color-warning-soft, #fdefd9); color: var(--b2s-color-warning-strong, #9a5b00); font-size: var(--b2s-fs-sm); font-weight: 600; }
</style>
