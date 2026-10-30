<script context="module" lang="ts">
  // Kept across visits: coming back from a folder returns to the same level, filter and page
  const memory = {
    zone: null as string | null,
    server: null as string | null,
    filter: 'all' as Filter,
    page: 0,
    open: new Set<string>()
  };
  type Filter = 'all' | 'review' | 'blocking' | 'pending' | 'no-inheritance';
</script>

<script lang="ts">
  import { onMount } from 'svelte';
  import { t } from '$lib/i18n';
  import StorageRootContextMenu from '$lib/components/storage-roots/StorageRootContextMenu.svelte';
  import type { FolderActionKind } from '$lib/components/storage-roots/StorageRootFolderActions.svelte';
  import type { StorageRootRow } from '$lib/utils/storage-roots';

  type Alert = { count: number; tone: 'warning' | 'error'; label?: string } | null;
  type Tone = 'ok' | 'warn' | 'bad' | 'read';
  type RowState = { blocking: boolean; review: boolean; pending: number; alerts: number; tone: Tone; label: string };
  type Totals = { n: number; review: number; blocking: number; pending: number };
  type Tile = { key: string; name: string; sub?: string; totals: Totals; big?: number; note: string; row?: StorageRootRow; pick: () => void };
  type Line = { key: string; name: string; sub?: string; depth: number; group: boolean; totals: Totals; row?: StorageRootRow };

  /**
   * Home of the folders: tiles level by level (zone > server > folder) or a tree list,
   * made for hundreds of folders; a folder opens on the detail page.
   */
  export let rows: StorageRootRow[] = [];
  export let query = '';
  export let rootAlertSummary: (row: StorageRootRow) => Alert = () => null;
  export let onQueryChange: (value: string) => void = () => {};
  export let onOpenRoot: (id: number) => void = () => {};
  export let onRequestAccess: (id: number) => void = () => {};
  export let onAdd: (() => void) | null = null;
  export let onFolderAction: ((kind: FolderActionKind, row: StorageRootRow) => void) | null = null;

  const VIEW_KEY = 'b2s.storageRoots.browse';
  const TILE_LIMIT = 23;
  const PAGE_SIZE = 18;

  let view: 'tiles' | 'list' = 'tiles';
  let filter: Filter = memory.filter;
  let zoneKey: string | null = memory.zone;
  let serverKey: string | null = memory.server;
  let listPage = memory.page;
  let open = memory.open;
  let showAllTiles = false;
  let selected: StorageRootRow | null = null;
  let menuRow: StorageRootRow | null = null;
  let menuAt = { x: 0, y: 0 };

  onMount(() => {
    try {
      if (localStorage.getItem(VIEW_KEY) === 'list') view = 'list';
    } catch {
      // Storage unavailable: tiles by default
    }
  });

  function setView(next: 'tiles' | 'list'): void {
    view = next;
    try {
      localStorage.setItem(VIEW_KEY, next);
    } catch {
      // Not remembered
    }
  }

  $: memory.filter = filter;
  $: memory.zone = zoneKey;
  $: memory.server = serverKey;
  $: memory.page = listPage;

  const byName = (a: { name: string }, b: { name: string }): number =>
    a.name.localeCompare(b.name, 'fr', { sensitivity: 'base', numeric: true });
  const rootId = (row: StorageRootRow): number => Number(row?.storage_root_id ?? row?.id ?? 0);
  const rootName = (row: StorageRootRow): string =>
    String(row?.storage_root_name ?? row?.storage_root_code ?? t('Storage root')).trim() || t('Storage root');
  const rootPath = (row: StorageRootRow): string => String(row?.root_path ?? row?.normalized_root_path ?? '').trim();
  // \\server\share\folder (or /server/share/folder) -> [server, share, folder]
  const segments = (row: StorageRootRow): string[] => rootPath(row).split(/[\\/]+/).filter(Boolean);
  const serverName = (row: StorageRootRow): string =>
    String(row?.storage_endpoint_name ?? '').trim() || segments(row)[0] || t('Unknown server');
  const parentPath = (row: StorageRootRow): string => segments(row).slice(1, -1).join('\\');
  const distinctParents = (list: StorageRootRow[]): boolean => new Set(list.map(parentPath)).size > 1;
  const zoneIdOf = (row: StorageRootRow): string => String(row?.zone_id ?? 'unassigned-zone');
  const zoneName = (row: StorageRootRow): string => String(row?.zone_name ?? t('Unassigned zone')).trim() || t('Unassigned zone');
  const serverIdOf = (row: StorageRootRow): string => `${zoneIdOf(row)}|${(segments(row)[0] ?? serverName(row)).toLowerCase()}`;

  // Same reading as the explorer: red = blocking alert, orange = request to decide
  function stateOf(row: StorageRootRow): RowState {
    const alert = rootAlertSummary(row);
    const alerts = alert?.count ?? 0;
    const pending = Number(row?.pending_validation_count ?? 0);
    const blocking = alerts > 0 && alert?.tone === 'error';
    const alertLabel = t('{count} alert(s)', { count: alerts });
    if (blocking) return { blocking, review: true, pending, alerts, tone: 'bad', label: alertLabel };
    if (pending > 0) return { blocking, review: true, pending, alerts, tone: 'warn', label: t('{count} pending requests', { count: pending }) };
    if (alerts > 0) return { blocking, review: false, pending, alerts, tone: 'read', label: alertLabel };
    return { blocking, review: false, pending, alerts, tone: 'ok', label: t('Nothing to do') };
  }

  $: states = new Map(rows.map((row) => [rootId(row), stateOf(row)]));
  const stateFor = (map: Map<number, RowState>, row: StorageRootRow): RowState => map.get(rootId(row)) ?? stateOf(row);

  function totalsOf(map: Map<number, RowState>, list: StorageRootRow[]): Totals {
    const totals: Totals = { n: list.length, review: 0, blocking: 0, pending: 0 };
    for (const row of list) {
      const state = stateFor(map, row);
      if (state.review) totals.review += 1;
      if (state.blocking) totals.blocking += 1;
      if (state.pending > 0) totals.pending += 1;
    }
    return totals;
  }

  function passes(map: Map<number, RowState>, active: Filter, row: StorageRootRow): boolean {
    const state = stateFor(map, row);
    if (active === 'review') return state.review;
    if (active === 'blocking') return state.blocking;
    if (active === 'pending') return state.pending > 0;
    if (active === 'no-inheritance') return row?.inheritance_broken === true;
    return true;
  }

  function group<T>(list: StorageRootRow[], keyOf: (row: StorageRootRow) => string, build: (key: string, items: StorageRootRow[]) => T): T[] {
    const groups = new Map<string, StorageRootRow[]>();
    for (const row of list) {
      const key = keyOf(row);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(row);
    }
    return [...groups.entries()].map(([key, items]) => build(key, items));
  }

  function matches(row: StorageRootRow, needle: string): boolean {
    const tags = Array.isArray(row?.tags) ? row.tags.map((tag: any) => tag?.label ?? tag?.name ?? tag?.code) : [];
    return [rootName(row), rootPath(row), row?.storage_root_code, row?.storage_endpoint_name, zoneName(row), ...tags]
      .filter(Boolean)
      .join(' ')
      .toLowerCase()
      .includes(needle);
  }

  $: needle = query.trim().toLowerCase();
  $: visibleRows = rows.filter((row) => passes(states, filter, row));
  $: filters = [
    { key: 'all', label: t('All') },
    { key: 'review', label: t('To review') },
    { key: 'blocking', label: t('Blocking') },
    { key: 'pending', label: t('Pending requests') },
    { key: 'no-inheritance', label: t('No inheritance') }
  ].map((item) => ({
    ...item,
    key: item.key as Filter,
    count: rows.filter((row) => passes(states, item.key as Filter, row)).length
  }));
  $: allTotals = totalsOf(states, rows);
  $: zoneCount = new Set(rows.map(zoneIdOf)).size;
  $: serverCount = new Set(rows.map(serverIdOf)).size;

  // A single zone or server is not a choice: that level is skipped
  $: singleZone = zoneCount === 1;
  $: currentZone = singleZone ? zoneIdOf(rows[0]) : rows.some((row) => zoneIdOf(row) === zoneKey) ? zoneKey : null;
  $: zoneRows = currentZone == null ? [] : rows.filter((row) => zoneIdOf(row) === currentZone);
  $: singleServer = currentZone != null && new Set(zoneRows.map(serverIdOf)).size === 1;
  $: currentServer = currentZone == null
    ? null
    : singleServer
      ? serverIdOf(zoneRows[0])
      : zoneRows.some((row) => serverIdOf(row) === serverKey) ? serverKey : null;

  function goToZone(key: string | null): void {
    zoneKey = key;
    serverKey = null;
    showAllTiles = false;
    selected = null;
  }

  function goToServer(key: string | null): void {
    serverKey = key;
    showAllTiles = false;
    selected = null;
  }

  $: level = (() => {
    const scoped = visibleRows.filter((row) => currentZone == null || zoneIdOf(row) === currentZone);
    if (currentZone == null) {
      return group(scoped, zoneIdOf, (key, items): Tile => {
        const totals = totalsOf(states, items);
        const servers = new Set(items.map(serverIdOf)).size;
        return {
          key: `z:${key}`,
          name: zoneName(items[0]),
          totals,
          big: items.length,
          note: t('{servers} servers · {count} to review', { servers, count: totals.review }),
          pick: () => goToZone(key)
        };
      });
    }
    if (currentServer == null) {
      return group(scoped, serverIdOf, (key, items): Tile => {
        const totals = totalsOf(states, items);
        return {
          key: `s:${key}`,
          name: serverName(items[0]),
          totals,
          big: items.length,
          note: t('{count} to review', { count: totals.review }),
          pick: () => goToServer(key)
        };
      });
    }
    const folders = scoped.filter((row) => serverIdOf(row) === currentServer);
    const showParent = distinctParents(folders);
    return folders
      .map((row): Tile => ({
        key: `r:${rootId(row)}`,
        name: rootName(row),
        sub: showParent ? parentPath(row) : undefined,
        totals: totalsOf(states, [row]),
        note: stateFor(states, row).label,
        row,
        pick: () => (selected = row)
      }));
  })();
  $: isFolderLevel = currentZone != null && currentServer != null;
  $: sortedLevel = [...level].sort(
    (a, b) => b.totals.blocking - a.totals.blocking || (b.big ?? 0) - (a.big ?? 0) || b.totals.review - a.totals.review || byName(a, b)
  );
  $: shownTiles = showAllTiles ? sortedLevel : sortedLevel.slice(0, TILE_LIMIT);

  // The biggest zones and servers take more room; folders have no volume to compare
  const tileSpan = (index: number, folderLevel: boolean): string => {
    if (folderLevel) return '';
    const columns = index === 0 ? 3 : index < 3 ? 2 : 1;
    return `grid-column:span ${columns};grid-row:span ${index === 0 ? 2 : 1};`;
  };
  // Colour: share of what is to be done, red as soon as something blocks
  const tileHeat = (totals: Totals): string => {
    const share = totals.n ? totals.review / totals.n : 0;
    const percent = Math.round(Math.min(26, share * 70));
    return `background:color-mix(in srgb, var(${totals.blocking ? '--b2s-color-danger' : '--b2s-color-warning'}) ${percent}%, var(--b2s-color-surface));`;
  };

  function toggle(key: string): void {
    if (open.has(key)) open.delete(key);
    else open.add(key);
    open = open;
  }

  $: lines = (() => {
    const folderLine = (row: StorageRootRow, depth: number, sub: string): Line => ({
      key: `r:${rootId(row)}`,
      name: rootName(row),
      sub,
      depth,
      group: false,
      totals: totalsOf(states, [row]),
      row
    });
    if (needle) return visibleRows.filter((row) => matches(row, needle)).map((row) => folderLine(row, 0, rootPath(row))).sort(byName);
    const result: Line[] = [];
    const zones = group(visibleRows, zoneIdOf, (key, items) => ({ key: `z:${key}`, name: zoneName(items[0]), items })).sort(byName);
    for (const zone of zones) {
      result.push({ key: zone.key, name: zone.name, depth: 0, group: true, totals: totalsOf(states, zone.items) });
      if (!open.has(zone.key)) continue;
      const servers = group(zone.items, serverIdOf, (key, items) => ({ key: `s:${key}`, name: serverName(items[0]), items })).sort(byName);
      for (const server of servers) {
        result.push({ key: server.key, name: server.name, depth: 1, group: true, totals: totalsOf(states, server.items) });
        if (!open.has(server.key)) continue;
        const showParent = distinctParents(server.items);
        result.push(...server.items.map((row) => folderLine(row, 2, showParent ? parentPath(row) : '')).sort(byName));
      }
    }
    return result;
  })();
  $: pageCount = Math.max(1, Math.ceil(lines.length / PAGE_SIZE));
  $: if (listPage > pageCount - 1) listPage = pageCount - 1;
  $: pageLines = lines.slice(listPage * PAGE_SIZE, listPage * PAGE_SIZE + PAGE_SIZE);
  $: searching = needle.length > 0;
  $: showTiles = view === 'tiles' && !searching;

  function setFilter(next: Filter): void {
    filter = next;
    listPage = 0;
    showAllTiles = false;
  }

  function groupTone(totals: Totals): Tone {
    return totals.blocking ? 'bad' : totals.review ? 'warn' : 'ok';
  }
  const groupLabel = (totals: Totals): string =>
    totals.review ? t('{count} to review', { count: totals.review }) : t('Nothing to do');

  $: scopeRows = currentServer != null
    ? zoneRows.filter((row) => serverIdOf(row) === currentServer)
    : currentZone != null ? zoneRows : rows;
  $: scopeTotals = totalsOf(states, scopeRows);
  // The selected row may have been reloaded (rights, alerts): always read the latest one
  $: selectedRow = selected ? rows.find((row) => rootId(row) === rootId(selected as StorageRootRow)) ?? null : null;
  $: selectedState = selectedRow ? stateFor(states, selectedRow) : null;

  function openMenu(row: StorageRootRow, event: MouseEvent): void {
    if (!onFolderAction) return;
    event.preventDefault();
    menuRow = row;
    menuAt = { x: event.clientX, y: event.clientY };
  }
</script>

<div class="br">
  <header class="br__head">
    <div class="br__title">
      <h1>{t('Folders')}</h1>
      <p>
        {t('{folders} folders · {servers} servers · {zones} zones — {count} to review', {
          folders: rows.length,
          servers: serverCount,
          zones: zoneCount,
          count: allTotals.review
        })}
      </p>
    </div>
    <label class="br__search">
      <i class="bi bi-search" aria-hidden="true"></i>
      <input
        type="search"
        aria-label={t('Search all folders')}
        placeholder={t('Search all folders…')}
        value={query}
        on:input={(event) => {
          onQueryChange(event.currentTarget.value);
          listPage = 0;
        }}
      />
    </label>
    <div class="br__seg" role="group" aria-label={t('Display')}>
      <button type="button" class:on={view === 'tiles'} aria-pressed={view === 'tiles'} on:click={() => setView('tiles')}>{t('Tiles')}</button>
      <button type="button" class:on={view === 'list'} aria-pressed={view === 'list'} on:click={() => setView('list')}>{t('List')}</button>
    </div>
    {#if onAdd}
      <button type="button" class="br__btn br__btn--primary" on:click={onAdd}>
        <i class="bi bi-plus-lg" aria-hidden="true"></i>{t('Add folders')}
      </button>
    {/if}
  </header>

  <div class="br__chips" role="group" aria-label={t('Filters')}>
    {#each filters as item (item.key)}
      <button type="button" class:on={filter === item.key} aria-pressed={filter === item.key} on:click={() => setFilter(item.key)}>
        {item.label} · {item.count}
      </button>
    {/each}
  </div>

  <div class="br__body">
    <div class="br__main">
      {#if showTiles}
        <nav class="br__crumb" aria-label={t('Level')}>
          {#if !singleZone}
            <button type="button" on:click={() => goToZone(null)}>{t('All zones')}</button>
          {/if}
          {#if currentZone != null}
            {#if !singleZone}<span aria-hidden="true">›</span>{/if}
            {#if currentServer != null && !singleServer}
              <button type="button" on:click={() => goToServer(null)}>{zoneName(zoneRows[0])}</button>
              <span aria-hidden="true">›</span>
              <strong>{serverName(scopeRows[0])}</strong>
            {:else if currentServer != null}
              <strong>{zoneName(zoneRows[0])} · {serverName(scopeRows[0])}</strong>
            {:else}
              <strong>{zoneName(zoneRows[0])}</strong>
            {/if}
          {/if}
          {#if !isFolderLevel}<small>{t('Size: volume · colour: share to review')}</small>{/if}
        </nav>

        {#if sortedLevel.length === 0}
          <p class="br__empty">{t('No folder matches your search.')}</p>
        {:else}
          <section class="br__tiles" aria-label={t('Tiles')}>
            {#each shownTiles as tile, index (tile.key)}
              <button
                type="button"
                class="br__tile"
                class:sel={tile.row && selectedRow && rootId(tile.row) === rootId(selectedRow)}
                style={`${tileSpan(index, isFolderLevel)}${tileHeat(tile.totals)}`}
                on:click={tile.pick}
                on:dblclick={() => tile.row && onOpenRoot(rootId(tile.row))}
                on:contextmenu={(event) => tile.row && openMenu(tile.row, event)}
              >
                <span class="br__tile-top">
                  <strong class:big={!isFolderLevel && index === 0} class:mid={!isFolderLevel && index > 0 && index < 3}>{tile.name}</strong>
                  {#if tile.big != null}<b>{tile.big}</b>{/if}
                </span>
                {#if tile.sub}<code title={tile.row ? rootPath(tile.row) : undefined}>{tile.sub}</code>{/if}
                <span class="br__tile-note">
                  <span>{tile.note}</span>
                  {#if tile.totals.blocking > 0 && !tile.row}
                    <em class="tag bad">{t('{count} blocking', { count: tile.totals.blocking })}</em>
                  {/if}
                  {#if tile.row?.inheritance_broken === true}<em class="tag">{t('No inheritance')}</em>{/if}
                </span>
              </button>
            {/each}
          </section>
          {#if !showAllTiles && sortedLevel.length > TILE_LIMIT}
            <button type="button" class="br__btn br__more" on:click={() => (showAllTiles = true)}>
              {t('Show the other {count}', { count: sortedLevel.length - TILE_LIMIT })}
            </button>
          {/if}
        {/if}
      {:else}
        <div class="br__panel br__table">
          <table>
            <thead>
              <tr><th>{t('Name')}</th><th class="w-state">{t('State')}</th><th class="w-num">{t('Requests')}</th><th class="w-inh">{t('Inheritance')}</th></tr>
            </thead>
            <tbody>
              {#each pageLines as line (line.key)}
                {@const state = line.row ? stateFor(states, line.row) : null}
                <tr
                  class:sel={line.row && selectedRow && rootId(line.row) === rootId(selectedRow)}
                  on:click={() => (line.group ? toggle(line.key) : (selected = line.row ?? null))}
                  on:dblclick={() => line.row && onOpenRoot(rootId(line.row))}
                  on:contextmenu={(event) => line.row && openMenu(line.row, event)}
                >
                  <td>
                    <div class="br__cell" style={`padding-left:${line.depth * 24}px`}>
                      {#if line.group}
                        <button type="button" class="br__caret" aria-expanded={open.has(line.key)} aria-label={open.has(line.key) ? t('Collapse') : t('Expand')}>
                          <i class={`bi ${open.has(line.key) ? 'bi-chevron-down' : 'bi-chevron-right'}`} aria-hidden="true"></i>
                        </button>
                        <strong class:zone={line.depth === 0}>{line.name}</strong>
                        <small>{line.totals.n}</small>
                      {:else}
                        <button type="button" class="br__name">
                          {line.name}
                          {#if line.sub}<code>{line.sub}</code>{/if}
                        </button>
                      {/if}
                    </div>
                  </td>
                  <td>
                    {#if state}
                      <span class={`tag ${state.tone}`}>{state.label}</span>
                    {:else}
                      <span class={`tag ${groupTone(line.totals)}`}>{groupLabel(line.totals)}</span>
                    {/if}
                  </td>
                  <td>{line.row ? state?.pending || '—' : line.totals.pending || '—'}</td>
                  <td class="muted">{line.row ? (line.row.inheritance_broken === true ? t('Disabled') : t('Inherited')) : ''}</td>
                </tr>
              {:else}
                <tr><td colspan="4" class="br__empty">{t('No folder matches your search.')}</td></tr>
              {/each}
            </tbody>
          </table>
          <div class="br__pager">
            <span>
              {#if lines.length}
                {t('{from}–{to} of {total}', { from: listPage * PAGE_SIZE + 1, to: Math.min(lines.length, listPage * PAGE_SIZE + PAGE_SIZE), total: lines.length })}
              {/if}
            </span>
            <button type="button" class="br__btn br__btn--sm" disabled={listPage === 0} on:click={() => (listPage -= 1)}>{t('Previous')}</button>
            <button type="button" class="br__btn br__btn--sm" disabled={listPage >= pageCount - 1} on:click={() => (listPage += 1)}>{t('Next')}</button>
          </div>
        </div>
      {/if}
    </div>

    <aside class="br__panel br__side" aria-label={t('Details')}>
      {#if selectedRow && selectedState}
        <div>
          <span class={`tag ${selectedState.tone}`}>{selectedState.label}</span>
          <h2>{rootName(selectedRow)}</h2>
          <code>{rootPath(selectedRow) || '—'}</code>
        </div>
        <dl>
          <div><dt>{t('Zone')}</dt><dd>{zoneName(selectedRow)}</dd></div>
          <div><dt>{t('Server')}</dt><dd>{serverName(selectedRow)}</dd></div>
          <div><dt>{t('Requests')}</dt><dd>{selectedState.pending}</dd></div>
          <div><dt>{t('Inheritance')}</dt><dd>{selectedRow.inheritance_broken === true ? t('Disabled') : t('Inherited')}</dd></div>
        </dl>
        <div class="br__actions">
          <button type="button" class="br__btn br__btn--primary" on:click={() => onOpenRoot(rootId(selectedRow))}>{t('Open the folder')}</button>
          <button type="button" class="br__btn" on:click={() => onRequestAccess(rootId(selectedRow))}>{t('Request access')}</button>
        </div>
      {:else}
        <div>
          <span class={`tag ${scopeTotals.blocking ? 'bad' : 'ok'}`}>
            {scopeTotals.blocking ? t('{count} blocking', { count: scopeTotals.blocking }) : t('Under control')}
          </span>
          <h2>
            {currentServer != null ? serverName(scopeRows[0]) : currentZone != null ? zoneName(zoneRows[0]) : t('All folders')}
          </h2>
        </div>
        <p>{t('{count} folders out of {total} need action.', { count: scopeTotals.review, total: scopeTotals.n })}</p>
        <dl>
          <div><dt>{t('Folders')}</dt><dd>{scopeTotals.n}</dd></div>
          <div><dt>{t('To review')}</dt><dd>{scopeTotals.review}</dd></div>
          <div><dt>{t('Blocking')}</dt><dd>{scopeTotals.blocking}</dd></div>
          <div><dt>{t('Pending requests')}</dt><dd>{scopeTotals.pending}</dd></div>
        </dl>
        {#if scopeTotals.review > 0 && filter !== 'review'}
          <button type="button" class="br__btn br__btn--primary" on:click={() => setFilter('review')}>{t('Show what needs action')}</button>
        {/if}
      {/if}
    </aside>
  </div>
</div>

<StorageRootContextMenu
  row={menuRow}
  at={menuAt}
  onClose={() => (menuRow = null)}
  onOpen={(row) => onOpenRoot(rootId(row))}
  onAction={(kind, row) => onFolderAction?.(kind, row)}
/>

<style>
  .br { display: flex; flex-direction: column; gap: 18px; padding: 24px 28px 36px; }
  .br__head { display: flex; align-items: flex-end; gap: 12px; }
  .br__title { flex: 1 1 320px; min-width: 0; }
  .br__title h1 { margin: 0; font-size: 38px; line-height: 1.05; font-weight: 600; letter-spacing: -.03em; }
  .br__title p { margin: 6px 0 0; color: var(--b2s-color-text-muted); font-size: 15px; }
  .br__search { flex: 0 1 380px; display: flex; align-items: center; gap: 10px; min-height: 44px; padding: 0 14px; border-radius: 12px; background: var(--b2s-color-surface); border: 1px solid var(--b2s-color-border-strong); color: var(--b2s-color-text-muted); }
  .br__search:focus-within { border-color: var(--b2s-color-text); }
  .br__search input { flex: 1; min-width: 0; border: 0; outline: 0; background: transparent; color: var(--b2s-color-text); font: inherit; }
  .br__seg { display: inline-flex; gap: 3px; padding: 3px; border-radius: 12px; background: var(--b2s-color-neutral-soft); }
  .br__seg button { min-height: 38px; padding: 0 14px; border: 0; border-radius: 9px; background: transparent; color: var(--b2s-color-text-muted); font: inherit; font-weight: 500; cursor: pointer; }
  .br__seg button.on { background: var(--b2s-color-surface); color: var(--b2s-color-text); box-shadow: 0 1px 2px rgba(14, 18, 24, .12); }
  .br__btn { min-height: 44px; padding: 0 16px; border-radius: 12px; border: 1px solid var(--b2s-color-border-strong); background: var(--b2s-color-surface); color: var(--b2s-color-text); font: inherit; font-weight: 500; cursor: pointer; display: inline-flex; align-items: center; justify-content: center; gap: 8px; }
  .br__btn:hover:not(:disabled) { background: var(--b2s-color-surface-soft); }
  .br__btn:disabled { opacity: .5; cursor: default; }
  .br__btn--primary { background: var(--b2s-accent); color: var(--b2s-on-accent); border-color: #9ad632; font-weight: 600; }
  .br__btn--primary:hover:not(:disabled) { background: #abea3c; }
  .br__btn--sm { min-height: 36px; padding: 0 11px; font-size: 13px; border-radius: 10px; }
  .br__chips { display: flex; flex-wrap: wrap; gap: 8px; }
  .br__chips button { min-height: 36px; padding: 0 13px; border-radius: 999px; border: 1px solid var(--b2s-color-border-strong); background: var(--b2s-color-surface); color: var(--b2s-color-text-muted); font: inherit; font-size: 13px; cursor: pointer; white-space: nowrap; }
  .br__chips button:hover { color: var(--b2s-color-text); }
  .br__chips button.on { background: var(--b2s-color-text); border-color: var(--b2s-color-text); color: #fff; font-weight: 600; }
  .br__body { display: flex; gap: 18px; align-items: flex-start; }
  .br__main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 12px; }
  .br__crumb { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; font-size: 14px; color: var(--b2s-color-text-muted); }
  .br__crumb button { padding: 0; border: 0; background: none; font: inherit; color: inherit; cursor: pointer; }
  .br__crumb button:hover { color: var(--b2s-color-text); text-decoration: underline; }
  .br__crumb strong { font-weight: 500; color: var(--b2s-color-text); }
  .br__crumb small { margin-left: auto; font-size: 12px; }
  .br__tiles { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); grid-auto-flow: dense; gap: 10px; }
  .br__tile { min-width: 0; min-height: 112px; padding: 14px; display: flex; flex-direction: column; justify-content: space-between; align-items: stretch; gap: 10px; text-align: left; font: inherit; color: var(--b2s-color-text); border: 1px solid var(--b2s-color-border); border-radius: 16px; cursor: pointer; transition: transform .12s, box-shadow .12s; }
  .br__tile:hover { transform: translateY(-2px); box-shadow: 0 1px 2px rgba(14, 18, 24, .05), 0 8px 24px rgba(14, 18, 24, .06); }
  .br__tile.sel { border-color: var(--b2s-color-text); box-shadow: 0 0 0 1px var(--b2s-color-text); }
  .br__tile-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; }
  .br__tile-top strong { min-width: 0; font-size: 14px; font-weight: 600; letter-spacing: -.01em; overflow-wrap: anywhere; }
  .br__tile-top strong.mid { font-size: 17px; }
  .br__tile-top strong.big { font-size: 22px; }
  .br__tile-top b { font-size: 22px; font-weight: 600; letter-spacing: -.02em; line-height: 1; }
  .br__tile code { font-family: var(--b2s-font-mono); font-size: 11px; color: var(--b2s-color-text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .br__tile-note { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; min-height: 22px; font-size: 12px; }
  .br__more { align-self: center; }
  .br__panel { background: var(--b2s-color-surface); border: 1px solid var(--b2s-color-border); border-radius: 18px; box-shadow: 0 1px 2px rgba(14, 18, 24, .05), 0 8px 24px rgba(14, 18, 24, .06); }
  .br__table { overflow: hidden; }
  .br__table table { width: 100%; border-collapse: collapse; }
  .br__table th { text-align: left; font-size: 12px; font-weight: 500; color: var(--b2s-color-text-muted); padding: 10px 14px; border-bottom: 1px solid var(--b2s-color-border); }
  .br__table td { padding: 10px 14px; border-bottom: 1px solid var(--b2s-color-border); vertical-align: middle; }
  .br__table tbody tr { cursor: pointer; }
  .br__table tbody tr:hover td { background: var(--b2s-color-surface-soft); }
  .br__table tbody tr.sel td { background: var(--b2s-accent-soft); }
  .w-state { width: 200px; }
  .w-num { width: 100px; }
  .w-inh { width: 110px; }
  .muted { font-size: 12px; color: var(--b2s-color-text-muted); }
  .br__cell { display: flex; align-items: center; gap: 6px; min-width: 0; }
  .br__cell strong { font-weight: 500; }
  .br__cell strong.zone { font-weight: 600; }
  .br__cell small { font-size: 12px; color: var(--b2s-color-text-muted); }
  .br__caret { width: 26px; height: 26px; flex: none; border: 0; border-radius: 7px; background: transparent; color: var(--b2s-color-text-muted); cursor: pointer; }
  .br__caret:hover { background: var(--b2s-color-border); }
  .br__name { min-width: 0; padding: 0; border: 0; background: none; color: inherit; font: inherit; text-align: left; cursor: pointer; }
  .br__name code { display: block; font-family: var(--b2s-font-mono); font-size: 12px; color: var(--b2s-color-text-muted); overflow-wrap: anywhere; }
  .br__pager { display: flex; align-items: center; gap: 6px; padding: 12px 14px; font-size: 12px; color: var(--b2s-color-text-muted); }
  .br__pager span { margin-right: auto; }
  .br__empty { margin: 0; padding: 24px; text-align: center; color: var(--b2s-color-text-muted); }
  .br__side { flex: 0 0 340px; position: sticky; top: 16px; padding: 20px; display: flex; flex-direction: column; gap: 16px; }
  .br__side h2 { margin: 10px 0 4px; font-size: 25px; font-weight: 600; letter-spacing: -.02em; overflow-wrap: anywhere; }
  .br__side code { font-family: var(--b2s-font-mono); font-size: 12px; color: var(--b2s-color-text-muted); overflow-wrap: anywhere; }
  .br__side p { margin: 0; font-size: 15px; }
  .br__side dl { margin: 0; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px 10px; }
  .br__side dt { font-size: 12px; font-weight: 400; color: var(--b2s-color-text-muted); }
  .br__side dd { margin: 0; font-weight: 500; overflow-wrap: anywhere; }
  .br__actions { display: flex; flex-wrap: wrap; gap: 8px; }
  .br__actions .br__btn--primary { flex: 1 1 auto; }
  .tag { display: inline-flex; align-items: center; font-size: 12px; font-style: normal; font-weight: 500; padding: 3px 9px; border-radius: 999px; background: var(--b2s-color-surface-soft); color: var(--b2s-color-text); white-space: nowrap; }
  .tag.ok { background: var(--b2s-color-success-soft); color: var(--b2s-color-success); }
  .tag.warn { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning); }
  .tag.bad { background: var(--b2s-color-danger-soft); color: var(--b2s-color-danger); }
  .tag.read { background: var(--b2s-color-info-soft); color: var(--b2s-color-info); }
</style>
