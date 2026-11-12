<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { t } from '$lib/i18n';
  import { apiGetData } from '$lib/api/client';
  import { formatBytes, formatDateTime } from '$lib/utils/format';
  import { csvFilename, downloadCsv } from '$lib/utils/csv';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';

  /**
   * Explorer of a scanned folder, down to the deepest level: blocks sized by volume (coloured by the 5S lens) or
   * a file-explorer list; a click shows, a double-click (or the name in the list) goes inside.
   */
  type Folder = { path: string; parent: string | null; name: string; depth: number; bytes: number; files: number; folders: number;
    direct_bytes: number; direct_files: number; cold1_bytes: number; cold3_bytes: number; last_modified: string | null;
    last_access?: string | null; created_at?: string | null };
  type FileRow = { path: string; name: string; size: number; modified: string | null };
  type Level = { node: Folder | null; children: Folder[]; files: FileRow[] };

  let rootName = '';
  let level: Level | null = null;
  let loading = true;
  let busy = false;
  let error: string | null = null;
  let trail: Folder[] = [];
  let selected: Folder | null = null;
  let colourBy: 'age' | 'old3' = 'age';
  let view: 'blocks' | 'list' = 'list';
  let sortBy: 'bytes' | 'name' | 'files' | 'last' = 'bytes';
  let width = 900;
  const HEIGHT = 520;

  $: rootId = Number($page.params.id);

  async function load(path: string | null): Promise<Level | null> {
    return apiGetData<Level>(fetch, `/modules/fives/storage-roots/${rootId}/folders`, path == null ? undefined : { path });
  }

  onMount(async () => {
    try {
      try {
        view = (localStorage.getItem('b2s.fives.explorer.view') as 'blocks' | 'list') || 'list';
      } catch {
        // Storage unavailable: the list
      }
      const overview = await apiGetData<Record<string, any>>(fetch, `/storage-roots/${rootId}/overview`);
      rootName = String(overview?.storage_root_name ?? `#${rootId}`);
      level = await load(null);
      if (level?.node) {
        trail = [level.node];
        selected = level.node;
      }
    } catch {
      error = t('Unable to load the scanned tree of this folder.');
    } finally {
      loading = false;
    }
  });

  function setView(next: 'blocks' | 'list') {
    view = next;
    try {
      localStorage.setItem('b2s.fives.explorer.view', next);
    } catch {
      // Not remembered
    }
  }

  async function enter(folder: Folder) {
    if (busy) return;
    busy = true;
    try {
      const next = await load(folder.path);
      if (next?.node) {
        level = next;
        trail = [...trail, next.node];
        selected = next.node;
      }
    } finally {
      busy = false;
    }
  }
  async function up(index: number) {
    if (busy || index === trail.length - 1) return;
    busy = true;
    try {
      const target = trail[index];
      const next = await load(index === 0 ? null : target.path);
      if (next?.node) {
        level = next;
        trail = trail.slice(0, index + 1);
        selected = next.node;
      }
    } finally {
      busy = false;
    }
  }

  $: current = level?.node ?? null;
  // Content of the folder clicked (without entering it), in the pane on the right
  let preview: Level | null = null;
  let previewFor = '';
  $: if (selected && current && selected.path !== current.path && selected.path !== previewFor) void loadPreview(selected);
  $: if (selected && current && selected.path === current.path) { preview = level; previewFor = current.path; }
  async function loadPreview(folder: Folder) {
    previewFor = folder.path;
    preview = null;
    const next = await load(folder.path).catch(() => null);
    if (previewFor === folder.path) preview = next;
  }
  $: children = [...(level?.children ?? [])].sort((a, b) =>
    sortBy === 'name' ? a.name.localeCompare(b.name, 'fr', { numeric: true })
      : sortBy === 'files' ? b.files - a.files
        : sortBy === 'last' ? String(b.last_modified ?? '').localeCompare(String(a.last_modified ?? ''))
          : b.bytes - a.bytes);
  $: files = [...(level?.files ?? [])].sort((a, b) =>
    sortBy === 'name' ? a.name.localeCompare(b.name, 'fr', { numeric: true })
      : sortBy === 'last' ? String(b.modified ?? '').localeCompare(String(a.modified ?? '')) : b.size - a.size);

  // Squarified treemap: rectangles close to squares, the biggest first
  type Box = { node: Folder; x: number; y: number; w: number; h: number };
  function layout(items: Folder[], x: number, y: number, w: number, h: number): Box[] {
    const list = items.filter((item) => item.bytes > 0).sort((a, b) => b.bytes - a.bytes);
    const total = list.reduce((sum, item) => sum + item.bytes, 0);
    if (!list.length || total <= 0 || w <= 0 || h <= 0) return [];
    const scale = (w * h) / total;
    const boxes: Box[] = [];
    let rest = list;
    while (rest.length) {
      const short = Math.min(w, h);
      let row: Folder[] = [];
      let best = Infinity;
      for (const item of rest) {
        const next = [...row, item];
        const area = next.reduce((sum, n) => sum + n.bytes * scale, 0);
        const worst = Math.max(...next.map((n) => Math.max((short * short * n.bytes * scale) / (area * area), (area * area) / (short * short * n.bytes * scale))));
        if (worst > best) break;
        best = worst;
        row = next;
      }
      const area = row.reduce((sum, n) => sum + n.bytes * scale, 0);
      const thick = area / short;
      let offset = 0;
      for (const node of row) {
        const length = (node.bytes * scale) / thick;
        boxes.push(w >= h ? { node, x, y: y + offset, w: thick, h: length } : { node, x: x + offset, y, w: length, h: thick });
        offset += length;
      }
      if (w >= h) { x += thick; w -= thick; } else { y += thick; h -= thick; }
      rest = rest.slice(row.length);
    }
    return boxes;
  }
  $: boxes = view === 'blocks' ? layout(level?.children ?? [], 0, 0, width, HEIGHT) : [];

  const pct = (part: number, whole: number) => (whole ? Math.round((part / whole) * 100) : 0);
  const oldShare = (folder: Folder) => (folder.bytes ? (colourBy === 'age' ? folder.cold1_bytes : folder.cold3_bytes) / folder.bytes : 0);
  const colour = (folder: Folder) => {
    const r = oldShare(folder);
    return `hsl(${210 - r * 205} ${45 + r * 35}% ${88 - r * 30}%)`;
  };
  const ageTone = (folder: Folder) => (oldShare(folder) > 0.8 ? 'is-old' : oldShare(folder) > 0.4 ? 'is-mid' : '');

  const exportLevel = () =>
    downloadCsv(csvFilename(`explorateur-${rootName}`), [
      { header: t('Type'), value: (row: any) => row.kind },
      { header: t('Path'), value: (row: any) => row.path },
      { header: t('Size'), value: (row: any) => row.size },
      { header: t('Files'), value: (row: any) => row.files ?? '' },
      { header: t('Not modified for 1 year'), value: (row: any) => row.cold1 ?? '' },
      { header: t('Last change'), value: (row: any) => row.last ?? '' }
    ], [
      ...children.map((f) => ({ kind: 'dossier', path: f.path, size: f.bytes, files: f.files, cold1: f.cold1_bytes, last: f.last_modified })),
      ...files.map((f) => ({ kind: 'fichier', path: f.path, size: f.size, files: null, cold1: null, last: f.modified }))
    ]);
</script>

<div class="ex">
  <div class="ex__top">
    <a class="b2s-btn b2s-btn-sm b2s-btn-secondary" href="/five-s"><i class="bi bi-arrow-left" aria-hidden="true"></i>{t('All the folders')}</a>
    <span class="ex__links">
      <a class="b2s-btn b2s-btn-sm b2s-btn-secondary" href={`/five-s/duplicates/${rootId}`}><i class="bi bi-files" aria-hidden="true"></i>{t('Duplicates')}</a>
      <a class="b2s-btn b2s-btn-sm b2s-btn-secondary" href={`/five-s/report/${rootId}`}><i class="bi bi-file-earmark-text" aria-hidden="true"></i>{t('Report')}</a>
    </span>
  </div>
  {#if loading}
    <LoadingState skeleton="rows" />
  {:else if error}
    <InlineAlert tone="error">{error}</InlineAlert>
  {:else if !current}
    <InlineAlert tone="info">{t('The detailed tree appears after the next measure of this folder with the 5S module (Measure on its page).')}</InlineAlert>
  {:else}
    <header class="ex__head">
      <nav class="ex__crumbs" aria-label={t('Path')}>
        {#each trail as step, index (step.path + index)}
          {#if index}<i class="bi bi-chevron-right" aria-hidden="true"></i>{/if}
          <button type="button" class:is-current={index === trail.length - 1} disabled={busy} on:click={() => up(index)}>{index === 0 ? rootName : step.name}</button>
        {/each}
        {#if busy}<span class="b2s-spinner b2s-spinner--sm" aria-hidden="true"></span>{/if}
      </nav>
      <div class="ex__tools">
        <div class="ex__seg" role="radiogroup" aria-label={t('View')}>
          <button type="button" class:is-on={view === 'list'} on:click={() => setView('list')}><i class="bi bi-list-ul" aria-hidden="true"></i>{t('Explorer')}</button>
          <button type="button" class:is-on={view === 'blocks'} on:click={() => setView('blocks')}><i class="bi bi-grid-1x2" aria-hidden="true"></i>{t('Blocks')}</button>
        </div>
        <div class="ex__seg" role="radiogroup" aria-label={t('Colour by')}>
          <button type="button" class:is-on={colourBy === 'age'} on:click={() => (colourBy = 'age')}>{t('Old > 1 year')}</button>
          <button type="button" class:is-on={colourBy === 'old3'} on:click={() => (colourBy = 'old3')}>{t('Old > 3 years')}</button>
        </div>
        <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-secondary" on:click={exportLevel}><i class="bi bi-download" aria-hidden="true"></i>{t('Export CSV')}</button>
      </div>
    </header>

    <div class="ex__body">
      {#if view === 'blocks'}
        <div class="ex__map" bind:clientWidth={width} style={`height:${HEIGHT}px`}>
          {#each boxes as box (box.node.path)}
            <button type="button" class="ex__box" class:is-sel={selected === box.node}
              style={`left:${box.x}px;top:${box.y}px;width:${Math.max(0, box.w - 2)}px;height:${Math.max(0, box.h - 2)}px;background:${colour(box.node)}`}
              title={`${box.node.name} · ${formatBytes(box.node.bytes)} · ${box.node.files.toLocaleString('fr-FR')} ${t('files')}`}
              on:click={() => (selected = box.node)} on:dblclick={() => box.node.folders > 0 && enter(box.node)}>
              {#if box.w > 70 && box.h > 34}
                <b>{box.node.name}</b>
                <small>{formatBytes(box.node.bytes)}{box.h > 52 ? ` · ${pct(box.node.bytes, current.bytes)} %` : ''}</small>
                {#if box.node.folders > 0 && box.h > 70}<span class="ex__in"><i class="bi bi-folder2" aria-hidden="true"></i>{box.node.folders}</span>{/if}
              {/if}
            </button>
          {:else}
            <p class="ex__empty">{t('No sub-folder here: see its files in the Explorer view.')}</p>
          {/each}
        </div>
      {:else}
        <div class="ex__list">
          <table class="b2s-table">
            <thead>
              <tr>
                <th><button type="button" class="ex__sort" class:is-on={sortBy === 'name'} on:click={() => (sortBy = 'name')}>{t('Name')}</button></th>
                <th class="ex__num"><button type="button" class="ex__sort" class:is-on={sortBy === 'bytes'} on:click={() => (sortBy = 'bytes')}>{t('Size')}</button></th>
                <th class="ex__num"><button type="button" class="ex__sort" class:is-on={sortBy === 'files'} on:click={() => (sortBy = 'files')}>{t('Files')}</button></th>
                <th class="ex__num">{t('Old > 1 year')}</th>
                <th class="ex__num"><button type="button" class="ex__sort" class:is-on={sortBy === 'last'} on:click={() => (sortBy = 'last')}>{t('Last change')}</button></th>
                <th class="ex__num">{t('Last access')}</th>
                <th class="ex__num">{t('Created')}</th>
              </tr>
            </thead>
            <tbody>
              {#each children as folder (folder.path)}
                <tr class="ex__row" class:is-sel={selected === folder} on:click={() => (selected = folder)} on:dblclick={() => folder.folders > 0 && enter(folder)}>
                  <td class="ex__name">
                    <i class="bi bi-folder-fill ex__folder" aria-hidden="true"></i>
                    {#if folder.folders > 0}<button type="button" class="b2s-link-btn" on:click|stopPropagation={() => enter(folder)}>{folder.name}</button>{:else}<span>{folder.name}</span>{/if}
                    {#if folder.folders > 0}<small>{t('{count} sub-folder(s)', { count: folder.folders })}</small>{/if}
                  </td>
                  <td class="ex__num">{formatBytes(folder.bytes)}</td>
                  <td class="ex__num">{folder.files.toLocaleString('fr-FR')}</td>
                  <td class={`ex__num ${ageTone(folder)}`}>{pct(folder.cold1_bytes, folder.bytes)} %</td>
                  <td class="ex__num">{folder.last_modified ? formatDateTime(folder.last_modified) : '—'}</td>
                  <td class="ex__num">{folder.last_access ? formatDateTime(folder.last_access) : '—'}</td>
                  <td class="ex__num">{folder.created_at ? formatDateTime(folder.created_at) : '—'}</td>
                </tr>
              {/each}
              {#each files as file (file.path)}
                <tr class="ex__row is-file">
                  <td class="ex__name"><i class="bi bi-file-earmark" aria-hidden="true"></i><code title={file.path}>{file.name}</code></td>
                  <td class="ex__num">{formatBytes(file.size)}</td>
                  <td class="ex__num">—</td>
                  <td class="ex__num">—</td>
                  <td class="ex__num">{file.modified ? formatDateTime(file.modified) : '—'}</td>
                  <td class="ex__num">—</td>
                  <td class="ex__num">—</td>
                </tr>
              {/each}
              {#if !children.length && !files.length}<tr><td colspan="7" class="ex__empty">{t('Nothing more known here.')}</td></tr>{/if}
            </tbody>
          </table>
          {#if current.direct_files > files.length}
            <p class="ex__hint">{t('{count} file(s) right in this folder ({size}); the files of 1 MB and more are listed.', { count: current.direct_files.toLocaleString('fr-FR'), size: formatBytes(current.direct_bytes) })}</p>
          {/if}
        </div>
      {/if}

      <aside class="ex__side">
        {#if selected}
          <h2>{selected === trail[0] ? rootName : selected.name}</h2>
          {#if selected !== current && selected.folders > 0}
            <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-primary" disabled={busy} on:click={() => selected && enter(selected)}><i class="bi bi-box-arrow-in-down-right" aria-hidden="true"></i>{t('Open ({count} sub-folders)', { count: selected.folders })}</button>
          {/if}
          <dl>
            <dt>{t('Volume')}</dt><dd>{formatBytes(selected.bytes)} <small>{pct(selected.bytes, trail[0]?.bytes ?? 0)} % {t('of the folder')}</small></dd>
            <dt>{t('Files')}</dt><dd>{selected.files.toLocaleString('fr-FR')}</dd>
            <dt>{t('Sub-folders')}</dt><dd>{selected.folders.toLocaleString('fr-FR')}</dd>
            <dt>{t('Right in it')}</dt><dd>{selected.direct_files.toLocaleString('fr-FR')} · {formatBytes(selected.direct_bytes)}</dd>
            <dt>{t('Last change')}</dt><dd>{selected.last_modified ? formatDateTime(selected.last_modified) : '—'}</dd>
            <dt>{t('Last access')}</dt><dd>{selected.last_access ? formatDateTime(selected.last_access) : t('not measured yet')}</dd>
            <dt>{t('Created')}</dt><dd>{selected.created_at ? formatDateTime(selected.created_at) : t('not measured yet')}</dd>
            <dt>{t('Not modified for 1 year')}</dt><dd>{formatBytes(selected.cold1_bytes)} <small>{pct(selected.cold1_bytes, selected.bytes)} %</small></dd>
            <dt>{t('Not modified for 3 years')}</dt><dd>{formatBytes(selected.cold3_bytes)} <small>{pct(selected.cold3_bytes, selected.bytes)} %</small></dd>
          </dl>
          <p class="ex__path"><code>{selected.path || '\\'}</code></p>
          <h3>{t('Content')}</h3>
          {#if !preview}
            <p class="ex__hint">{t('Loading…')}</p>
          {:else}
            <ul class="ex__content">
              {#each preview.children.slice(0, 12) as child (child.path)}
                <li><i class="bi bi-folder-fill ex__folder" aria-hidden="true"></i>
                  <button type="button" class="b2s-link-btn" on:click={() => enter(child)} disabled={child.folders === 0 && !child.direct_files}>{child.name}</button>
                  <span>{formatBytes(child.bytes)}</span></li>
              {/each}
              {#each preview.files.slice(0, 12) as file (file.path)}
                <li><i class="bi bi-file-earmark" aria-hidden="true"></i><code title={file.path}>{file.name}</code><span>{formatBytes(file.size)}</span></li>
              {/each}
              {#if !preview.children.length && !preview.files.length}<li class="ex__hint">{t('Nothing more known here.')}</li>{/if}
            </ul>
            {#if preview.children.length > 12 || preview.files.length > 12}<p class="ex__hint">{t('{folders} sub-folder(s) and {files} big file(s) in all: open the folder to see everything.', { folders: preview.children.length, files: preview.files.length })}</p>{/if}
          {/if}
          <p class="ex__hint">{t('Click to see a folder, double-click (or its name) to go inside. The colour tells the share of old data.')}</p>
        {/if}
      </aside>
    </div>
  {/if}
</div>

<style>
  .ex { display: grid; gap: 14px; }
  .ex__top { display: flex; justify-content: space-between; font-size: var(--b2s-fs-sm); }
  .ex__top a { display: inline-flex; gap: 6px; align-items: center; }
  .ex__head { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; justify-content: space-between; }
  .ex__crumbs { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; font-size: 16px; }
  .ex__crumbs button { border: 0; background: none; padding: 2px 4px; color: var(--b2s-color-primary, #2563eb); cursor: pointer; font: inherit; }
  .ex__crumbs button.is-current { color: inherit; font-weight: 600; cursor: default; }
  .ex__crumbs i { color: var(--b2s-color-text-muted); font-size: 12px; }
  .ex__tools { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
  .ex__seg { display: inline-flex; padding: 2px; border: 1px solid var(--b2s-color-border); border-radius: 999px; background: var(--b2s-color-surface, #fff); }
  .ex__seg button { display: inline-flex; gap: 6px; align-items: center; padding: 4px 10px; border: 0; border-radius: 999px; background: none; cursor: pointer; font-size: var(--b2s-fs-sm); }
  .ex__seg button.is-on { background: var(--b2s-topbar-bg, #0e1218); color: #fff; }
  .ex__body { display: grid; grid-template-columns: minmax(0, 1fr) 320px; gap: 14px; align-items: start; }
  .ex__map { position: relative; overflow: hidden; border-radius: 12px; background: var(--b2s-color-border-soft, #eef1f5); }
  .ex__box { position: absolute; display: flex; flex-direction: column; align-items: flex-start; gap: 2px; padding: 8px 10px; border: 0; border-radius: 8px;
    color: #1f2937; text-align: left; overflow: hidden; cursor: pointer; transition: filter 0.15s ease, box-shadow 0.15s ease; }
  .ex__box:hover { filter: brightness(0.96); box-shadow: inset 0 0 0 2px rgba(15, 23, 42, 0.35); }
  .ex__box.is-sel { box-shadow: inset 0 0 0 3px #0e1218; }
  .ex__box b { max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
  .ex__box small { font-size: 11px; opacity: 0.8; }
  .ex__in { position: absolute; right: 8px; bottom: 6px; display: inline-flex; gap: 4px; align-items: center; font-size: 11px; opacity: 0.7; }
  .ex__list { overflow: auto; border: 1px solid var(--b2s-color-border); border-radius: 12px; background: var(--b2s-color-surface, #fff); }
  .ex__row { cursor: default; }
  .ex__row:hover td { background: var(--b2s-color-surface-hover, #f5f8fc); }
  .ex__row.is-sel td { background: #e8efff; }
  .ex__name { display: flex; gap: 8px; align-items: center; min-width: 0; }
  .ex__name small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); white-space: nowrap; }
  .ex__name code { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: var(--b2s-fs-xs); max-width: 520px; }
  .ex__folder { color: #e0a526; }
  .ex__sort { border: 0; background: none; padding: 0; font: inherit; font-weight: 600; cursor: pointer; color: inherit; }
  .ex__sort.is-on { text-decoration: underline; }
  .ex__num { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }
  .ex__num.is-mid { color: #b45309; }
  .ex__num.is-old { color: #b42318; font-weight: 600; }
  .ex__empty { padding: 24px; color: var(--b2s-color-text-muted); text-align: center; }
  .ex__side { position: sticky; top: 12px; padding: 16px; border: 1px solid var(--b2s-color-border); border-radius: 12px; background: var(--b2s-color-surface, #fff); }
  .ex__side h2 { margin: 0 0 10px; font-size: 17px; overflow-wrap: anywhere; }
  .ex__side dl { display: grid; grid-template-columns: auto 1fr; gap: 6px 12px; margin: 12px 0 0; font-size: var(--b2s-fs-sm); }
  .ex__side dt { color: var(--b2s-color-text-muted); }
  .ex__side dd { margin: 0; text-align: right; }
  .ex__side dd small { color: var(--b2s-color-text-muted); }
  .ex__links { display: inline-flex; gap: 16px; }
  .ex__side h3 { margin: 14px 0 6px; font-size: var(--b2s-fs-xs); text-transform: uppercase; letter-spacing: 0.04em; color: var(--b2s-color-text-muted); }
  .ex__content { display: grid; gap: 4px; margin: 0; padding: 0; list-style: none; font-size: var(--b2s-fs-sm); }
  .ex__content li { display: grid; grid-template-columns: 16px minmax(0, 1fr) auto; gap: 8px; align-items: center; }
  .ex__content code, .ex__content button { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; text-align: left; font-size: var(--b2s-fs-xs); }
  .ex__content span { white-space: nowrap; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .ex__path code { font-size: var(--b2s-fs-xs); overflow-wrap: anywhere; }
  .ex__hint { margin: 10px 12px; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
</style>
