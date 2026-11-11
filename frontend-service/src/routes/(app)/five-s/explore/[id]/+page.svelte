<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { t } from '$lib/i18n';
  import { apiGetData } from '$lib/api/client';
  import { formatBytes, formatDateTime } from '$lib/utils/format';
  import FivesTabs from '$lib/components/fives/FivesTabs.svelte';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';

  /**
   * Explorer of a scanned folder: blocks sized by volume, coloured by what the 5S looks at (age, duplicates,
   * clutter); a click goes down. Two levels are known (the pieces of the scanner), then the biggest files.
   */
  type Chunk = { key: string; bytes: number; files: number; folders: number; last_modified: string | null;
    cold: Record<string, { bytes: number; files: number }>; junk: { bytes: number | null; files: number | null };
    duplicates_wasted: number; types: Array<{ ext: string; files: number; bytes?: number }> };
  type Node = { name: string; path: string[]; bytes: number; files: number; cold1: number; cold3: number; dup: number; junk: number;
    last: string | null; children: Node[]; leaf: boolean; types: Map<string, number> };
  type InvFile = { path: string; size: number; modified: string | null };

  let rootName = '';
  let rootPath = '';
  let tree: Node | null = null;
  let files: InvFile[] = [];
  let loading = true;
  let error: string | null = null;
  let trail: Node[] = [];
  let selected: Node | null = null;
  let colourBy: 'age' | 'duplicates' | 'clutter' = 'age';
  let width = 900;
  const HEIGHT = 520;

  $: rootId = Number($page.params.id);

  function blank(name: string, path: string[]): Node {
    return { name, path, bytes: 0, files: 0, cold1: 0, cold3: 0, dup: 0, junk: 0, last: null, children: [], leaf: false, types: new Map() };
  }
  function add(node: Node, chunk: Chunk) {
    node.bytes += chunk.bytes;
    node.files += chunk.files;
    node.cold1 += chunk.cold?.['1y']?.bytes ?? 0;
    node.cold3 += chunk.cold?.['3y']?.bytes ?? 0;
    node.dup += chunk.duplicates_wasted ?? 0;
    node.junk += chunk.junk?.bytes ?? 0;
    if (chunk.last_modified && (!node.last || chunk.last_modified > node.last)) node.last = chunk.last_modified;
    for (const type of chunk.types ?? []) node.types.set(type.ext, (node.types.get(type.ext) ?? 0) + (type.bytes ?? type.files));
  }
  /** The pieces of the scanner (« A », « ~A » + « A\\sub », « » for the files at the root) as a tree */
  function build(chunks: Chunk[]): Node {
    const root = blank(rootName, []);
    const level1 = new Map<string, Node>();
    for (const chunk of chunks) {
      add(root, chunk);
      if (!chunk.key) {
        const own = blank(t('(files of the folder)'), ['']);
        own.leaf = true;
        add(own, chunk);
        root.children.push(own);
        continue;
      }
      const flat = chunk.key.startsWith('~');
      const parts = chunk.key.replace(/^~/, '').split('\\');
      const first = parts[0];
      if (!level1.has(first)) {
        const node = blank(first, [first]);
        level1.set(first, node);
        root.children.push(node);
      }
      const parent = level1.get(first)!;
      add(parent, chunk);
      if (flat || parts.length > 1) {
        const child = blank(flat ? t('(files of « {name} »)', { name: first }) : parts[1], flat ? [first, ''] : [first, parts[1]]);
        child.leaf = true;
        add(child, chunk);
        parent.children.push(child);
      } else {
        parent.leaf = true;
      }
    }
    const sort = (node: Node) => {
      node.children.sort((a, b) => b.bytes - a.bytes);
      node.children.forEach(sort);
    };
    sort(root);
    return root;
  }

  onMount(async () => {
    try {
      const overview = await apiGetData<Record<string, any>>(fetch, `/storage-roots/${rootId}/overview`);
      rootName = String(overview?.storage_root_name ?? `#${rootId}`);
      rootPath = String(overview?.root_path ?? '');
      const [treeData, inventory] = await Promise.all([
        apiGetData<{ chunks: Chunk[] }>(fetch, `/modules/fives/storage-roots/${rootId}/tree`),
        apiGetData<{ files: InvFile[] }>(fetch, `/modules/fives/storage-roots/${rootId}/files`).catch(() => null)
      ]);
      files = inventory?.files ?? [];
      tree = build(treeData?.chunks ?? []);
      trail = [tree];
      selected = tree;
    } catch {
      error = t('Unable to load the scanned tree of this folder.');
    } finally {
      loading = false;
    }
  });

  $: current = trail[trail.length - 1] ?? null;

  // Squarified treemap: rectangles close to squares, the biggest first
  type Box = { node: Node; x: number; y: number; w: number; h: number };
  function layout(items: Node[], x: number, y: number, w: number, h: number): Box[] {
    const total = items.reduce((sum, item) => sum + item.bytes, 0);
    if (!items.length || total <= 0 || w <= 0 || h <= 0) return [];
    const scale = (w * h) / total;
    const boxes: Box[] = [];
    let rest = items.filter((item) => item.bytes > 0);
    while (rest.length) {
      const short = Math.min(w, h);
      let row: Node[] = [];
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
  $: boxes = current ? layout(current.children, 0, 0, width, HEIGHT) : [];

  /** Share of the block that the chosen 5S lens points at (0 → 1) */
  const ratio = (node: Node) =>
    !node.bytes ? 0 : colourBy === 'age' ? node.cold1 / node.bytes : colourBy === 'duplicates' ? Math.min(1, (node.dup / node.bytes) * 4) : Math.min(1, (node.junk / node.bytes) * 20);
  const colour = (node: Node) => {
    const r = ratio(node);
    // calm blue → amber → red as the share grows
    const hue = 210 - r * 205;
    return `hsl(${hue} ${45 + r * 35}% ${88 - r * 30}%)`;
  };
  const pct = (part: number, whole: number) => (whole ? Math.round((part / whole) * 100) : 0);

  function open(node: Node) {
    selected = node;
    if (!node.leaf && node.children.length) trail = [...trail, node];
  }
  function up(index: number) {
    trail = trail.slice(0, index + 1);
    selected = trail[trail.length - 1];
  }
  // The biggest files under the selected block (inventory: path relative to the share)
  $: prefix = selected?.path.filter(Boolean).join('\\') ?? '';
  $: underSelected = files
    .filter((file) => {
      const inside = rootPath ? file.path : file.path;
      if (!prefix) return true;
      const lower = inside.toLowerCase();
      return lower.includes(`\\${prefix.toLowerCase()}\\`) || lower.startsWith(`${prefix.toLowerCase()}\\`);
    })
    .slice(0, 12);
  $: topTypes = selected ? [...selected.types.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5) : [];
</script>

<FivesTabs />

<div class="ex">
  <div class="ex__top">
    <a href="/five-s"><i class="bi bi-arrow-left" aria-hidden="true"></i>{t('All the folders')}</a>
    <a href={`/five-s/report/${rootId}`}>{t('Report')} ›</a>
  </div>
  {#if loading}
    <LoadingState skeleton="rows" />
  {:else if error}
    <InlineAlert tone="error">{error}</InlineAlert>
  {:else if !tree || !tree.children.length}
    <InlineAlert tone="info">{t('No scanned tree yet: measure the folder with the 5S module on.')}</InlineAlert>
  {:else}
    <header class="ex__head">
      <nav class="ex__crumbs" aria-label={t('Path')}>
        {#each trail as step, index (index)}
          {#if index}<i class="bi bi-chevron-right" aria-hidden="true"></i>{/if}
          <button type="button" class:is-current={index === trail.length - 1} on:click={() => up(index)}>{index === 0 ? rootName : step.name}</button>
        {/each}
      </nav>
      <div class="ex__lens" role="radiogroup" aria-label={t('Colour by')}>
        <span>{t('Colour by')}</span>
        <button type="button" class:is-on={colourBy === 'age'} on:click={() => (colourBy = 'age')}><i class="bi bi-snow" aria-hidden="true"></i>{t('Age')}</button>
        <button type="button" class:is-on={colourBy === 'duplicates'} on:click={() => (colourBy = 'duplicates')}><i class="bi bi-files" aria-hidden="true"></i>{t('Duplicates')}</button>
        <button type="button" class:is-on={colourBy === 'clutter'} on:click={() => (colourBy = 'clutter')}><i class="bi bi-trash3" aria-hidden="true"></i>{t('Clutter')}</button>
      </div>
    </header>

    <div class="ex__body">
      <div class="ex__map" bind:clientWidth={width} style={`height:${HEIGHT}px`}>
        {#each boxes as box (box.node.path.join('/') + box.node.name)}
          <button type="button" class="ex__box" class:is-sel={selected === box.node} class:is-leaf={box.node.leaf}
            style={`left:${box.x}px;top:${box.y}px;width:${Math.max(0, box.w - 2)}px;height:${Math.max(0, box.h - 2)}px;background:${colour(box.node)}`}
            title={`${box.node.name} · ${formatBytes(box.node.bytes)} · ${box.node.files.toLocaleString('fr-FR')} ${t('files')}`}
            on:click={() => (selected = box.node)} on:dblclick={() => open(box.node)}>
            {#if box.w > 70 && box.h > 34}
              <b>{box.node.name}</b>
              <small>{formatBytes(box.node.bytes)}{box.h > 52 ? ` · ${pct(box.node.bytes, current?.bytes ?? 0)} %` : ''}</small>
              {#if !box.node.leaf && box.node.children.length && box.h > 70}<span class="ex__in"><i class="bi bi-box-arrow-in-down-right" aria-hidden="true"></i>{box.node.children.length}</span>{/if}
            {/if}
          </button>
        {/each}
      </div>

      <aside class="ex__side">
        {#if selected}
          <h2>{selected === tree ? rootName : selected.name}</h2>
          {#if !selected.leaf && selected.children.length && selected !== current}
            <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-primary" on:click={() => selected && open(selected)}><i class="bi bi-box-arrow-in-down-right" aria-hidden="true"></i>{t('Open ({count} sub-folders)', { count: selected.children.length })}</button>
          {/if}
          <dl>
            <dt>{t('Volume')}</dt><dd>{formatBytes(selected.bytes)} <small>{pct(selected.bytes, tree.bytes)} % {t('of the folder')}</small></dd>
            <dt>{t('Files')}</dt><dd>{selected.files.toLocaleString('fr-FR')}</dd>
            <dt>{t('Last change')}</dt><dd>{selected.last ? formatDateTime(selected.last) : '—'}</dd>
            <dt>{t('Not modified for 1 year')}</dt><dd>{formatBytes(selected.cold1)} <small>{pct(selected.cold1, selected.bytes)} %</small></dd>
            <dt>{t('Not modified for 3 years')}</dt><dd>{formatBytes(selected.cold3)} <small>{pct(selected.cold3, selected.bytes)} %</small></dd>
            <dt>{t('Lost to duplicates')}</dt><dd>{formatBytes(selected.dup)}</dd>
            <dt>{t('Clutter')}</dt><dd>{formatBytes(selected.junk)}</dd>
          </dl>
          {#if topTypes.length}
            <h3>{t('Main types')}</h3>
            <p class="ex__types">{#each topTypes as [ext] (ext)}<code>.{ext}</code>{/each}</p>
          {/if}
          <h3>{t('Biggest files here')}</h3>
          <ul class="ex__files">
            {#each underSelected as file (file.path)}
              <li><code title={file.path}>{file.path.split('\\').pop()}</code><span>{formatBytes(file.size)}</span></li>
            {:else}<li class="ex__none">{t('No big file known here.')}</li>{/each}
          </ul>
          <p class="ex__hint">{t('Click a block to see it, double-click to go inside. Colour: the share of old data, of duplicates or of clutter.')}</p>
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
  .ex__lens { display: flex; gap: 4px; align-items: center; font-size: var(--b2s-fs-sm); }
  .ex__lens span { margin-right: 4px; color: var(--b2s-color-text-muted); }
  .ex__lens button { display: inline-flex; gap: 6px; align-items: center; padding: 5px 10px; border: 1px solid var(--b2s-color-border); border-radius: 999px; background: var(--b2s-color-surface, #fff); cursor: pointer; }
  .ex__lens button.is-on { border-color: var(--b2s-topbar-bg, #0e1218); background: var(--b2s-topbar-bg, #0e1218); color: #fff; }
  .ex__body { display: grid; grid-template-columns: minmax(0, 1fr) 320px; gap: 14px; align-items: start; }
  .ex__map { position: relative; overflow: hidden; border-radius: 12px; background: var(--b2s-color-border-soft, #eef1f5); }
  .ex__box { position: absolute; display: flex; flex-direction: column; align-items: flex-start; justify-content: flex-start; gap: 2px; padding: 8px 10px;
    border: 0; border-radius: 8px; color: #1f2937; text-align: left; overflow: hidden; cursor: pointer; transition: filter 0.15s ease, box-shadow 0.15s ease; }
  .ex__box:hover { filter: brightness(0.96); box-shadow: inset 0 0 0 2px rgba(15, 23, 42, 0.35); }
  .ex__box.is-sel { box-shadow: inset 0 0 0 3px #0e1218; }
  .ex__box b { max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; }
  .ex__box small { font-size: 11px; opacity: 0.8; }
  .ex__in { position: absolute; right: 8px; bottom: 6px; display: inline-flex; gap: 4px; align-items: center; font-size: 11px; opacity: 0.7; }
  .ex__side { position: sticky; top: 12px; padding: 16px; border: 1px solid var(--b2s-color-border); border-radius: 12px; background: var(--b2s-color-surface, #fff); }
  .ex__side h2 { margin: 0 0 10px; font-size: 17px; overflow-wrap: anywhere; }
  .ex__side h3 { margin: 14px 0 6px; font-size: var(--b2s-fs-xs); text-transform: uppercase; letter-spacing: 0.04em; color: var(--b2s-color-text-muted); }
  .ex__side dl { display: grid; grid-template-columns: auto 1fr; gap: 6px 12px; margin: 12px 0 0; font-size: var(--b2s-fs-sm); }
  .ex__side dt { color: var(--b2s-color-text-muted); }
  .ex__side dd { margin: 0; text-align: right; }
  .ex__side dd small { color: var(--b2s-color-text-muted); }
  .ex__types { display: flex; flex-wrap: wrap; gap: 6px; margin: 0; }
  .ex__files { display: grid; gap: 4px; margin: 0; padding: 0; list-style: none; font-size: var(--b2s-fs-sm); }
  .ex__files li { display: flex; justify-content: space-between; gap: 8px; min-width: 0; }
  .ex__files code { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: var(--b2s-fs-xs); }
  .ex__files span { white-space: nowrap; color: var(--b2s-color-text-muted); }
  .ex__none { color: var(--b2s-color-text-muted); }
  .ex__hint { margin: 12px 0 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
</style>
