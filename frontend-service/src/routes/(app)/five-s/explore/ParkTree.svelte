<script lang="ts">
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { t } from '$lib/i18n';
  import { formatBytes } from '$lib/utils/format';
  import { inside, park, placeOf, toneOf, type ParkFolder } from './explore-state.svelte';

  /**
   * The tree of the explorer, beside every page of it: zones › servers › measured folders, then the sub-folders of
   * the folder open on its page. A zone or a server lists its folders in the table; a folder opens its content.
   */
  type Row = { key: string; depth: number; label: string; meta: string; caret: '' | 'open' | 'closed'; tone: string | null; on: boolean;
    kind: 'all' | 'zone' | 'server' | 'folder' | 'sub'; title: string; act: () => void };

  let query = $state('');
  let open = $state<Record<string, boolean>>({});
  let currentId = $derived(Number($page.params.id ?? 0) || null);
  let zone = $derived(currentId ? null : $page.url.searchParams.get('zone'));
  let server = $derived(currentId ? null : $page.url.searchParams.get('server'));
  let needle = $derived(query.trim().toLowerCase());
  let matching = $derived(park.folders.filter((f) => !needle || `${f.name} ${f.path} ${f.server ?? ''} ${f.zone ?? ''}`.toLowerCase().includes(needle)));
  let current = $derived(park.folders.find((f) => f.id === currentId) ?? null);

  // The way to the folder shown stays open; the first zone opens when nothing is chosen yet
  $effect(() => {
    const target = current ?? (zone ? park.folders.find((f) => placeOf(f.zone) === zone) : null) ?? (Object.keys(open).length ? null : park.folders[0]);
    if (!target) return;
    const z = `z:${placeOf(target.zone)}`;
    const s = `s:${placeOf(target.zone)}:${placeOf(target.server)}`;
    if (!open[z] || ((current || server) && !open[s])) open = { ...open, [z]: true, ...((current || server) ? { [s]: true } : {}) };
  });

  const sorted = (values: string[]) => [...new Set(values)].sort((a, b) => a.localeCompare(b));
  function scopeHref(z?: string, s?: string) {
    const params = new URLSearchParams();
    if (z) params.set('zone', z);
    if (s) params.set('server', s);
    const qs = params.toString();
    return `/five-s/explore${qs ? `?${qs}` : ''}`;
  }
  function openFolder(folder: ParkFolder) {
    // Already open: back to its top level (the page keeps its state)
    if (folder.id === currentId && inside.rootId === folder.id && inside.pick) inside.pick('t0');
    else void goto(`/five-s/explore/${folder.id}`);
  }

  let rows = $derived.by(() => {
    const out: Row[] = [{ key: 'all', depth: 0, label: t('All the folders'), meta: String(matching.length), caret: '', tone: null, kind: 'all', title: '',
      on: !currentId && !zone, act: () => void goto('/five-s/explore') }];
    for (const z of sorted(matching.map((f) => placeOf(f.zone)))) {
      const zFolders = matching.filter((f) => placeOf(f.zone) === z);
      const zOpen = needle !== '' || Boolean(open[`z:${z}`]);
      const zOn = !currentId && zone === z && !server;
      out.push({ key: `z:${z}`, depth: 0, label: z, meta: String(zFolders.length), caret: zOpen ? 'open' : 'closed', tone: null, kind: 'zone', title: '', on: zOn,
        act: () => { open = { ...open, [`z:${z}`]: !(zOn && zOpen) }; void goto(scopeHref(z)); } });
      if (!zOpen) continue;
      for (const s of sorted(zFolders.map((f) => placeOf(f.server)))) {
        const sFolders = zFolders.filter((f) => placeOf(f.server) === s);
        const sOpen = needle !== '' || Boolean(open[`s:${z}:${s}`]);
        const sOn = !currentId && zone === z && server === s;
        out.push({ key: `s:${z}:${s}`, depth: 1, label: s, meta: String(sFolders.length), caret: sOpen ? 'open' : 'closed', tone: null, kind: 'server', title: '', on: sOn,
          act: () => { open = { ...open, [`s:${z}:${s}`]: !(sOn && sOpen) }; void goto(scopeHref(z, s)); } });
        if (!sOpen) continue;
        for (const folder of [...sFolders].sort((a, b) => a.name.localeCompare(b.name))) {
          const isOpen = folder.id === currentId;
          const subs = isOpen && inside.rootId === folder.id ? inside.items.filter((item) => item.depth > 0) : [];
          const atTop = isOpen && (inside.items.find((item) => item.depth === 0)?.current ?? true);
          out.push({ key: `f:${folder.id}`, depth: 2, label: folder.name, meta: folder.size_bytes != null ? formatBytes(folder.size_bytes) : '', title: folder.path,
            caret: subs.length ? 'open' : '', tone: toneOf(folder.score), kind: 'folder', on: isOpen && atTop, act: () => openFolder(folder) });
          for (const item of subs) {
            out.push({ key: `i:${item.key}`, depth: 2 + item.depth, label: item.name, meta: formatBytes(item.bytes), caret: '', tone: null, kind: 'sub', title: item.name,
              on: item.current, act: () => inside.pick?.(item.key) });
          }
        }
      }
    }
    return out;
  });
</script>

<aside class="pt" aria-label={t('Tree of the measured folders')}>
  <label class="pt__find"><i class="bi bi-search" aria-hidden="true"></i>
    <input type="search" bind:value={query} placeholder={t('Filter the tree…')} aria-label={t('Filter the tree')} />
  </label>
  {#if park.loading && !park.folders.length}
    <p class="pt__note"><span class="b2s-spinner b2s-spinner--sm" aria-hidden="true"></span> {t('Loading…')}</p>
  {:else if park.error}
    <p class="pt__note">{park.error}</p>
  {:else}
    <div class="pt__rows">
      {#each rows as row (row.key)}
        <button type="button" class={`pt__row is-${row.kind}`} class:is-on={row.on} style={`padding-left:${8 + row.depth * 14}px`} title={row.title || undefined}
          aria-current={row.on ? 'page' : undefined} aria-expanded={row.caret ? row.caret === 'open' : undefined} onclick={row.act}>
          <span class="pt__car" aria-hidden="true">{row.caret === 'open' ? '▾' : row.caret === 'closed' ? '▸' : ''}</span>
          {#if row.tone}<span class={`v2-dw is-${row.tone}`} aria-hidden="true"></span>{:else if row.kind === 'sub'}<i class="bi bi-folder2" aria-hidden="true"></i>{/if}
          <span class="pt__label">{row.label}</span>
          <small>{row.meta}</small>
        </button>
      {:else}
        <p class="pt__note">{t('No measured folder here yet.')}</p>
      {/each}
    </div>
  {/if}
</aside>

<style>
  .pt { position: sticky; top: calc(var(--b2s-shell-top) + 12px); display: grid; gap: 8px; align-content: start; max-height: calc(100vh - var(--b2s-shell-top) - 60px); overflow: auto; margin: 26px 0 26px 24px;
    padding: 10px; border: 1px solid var(--b2s-color-border-soft, #e1e4ea); border-radius: 16px; background: var(--b2s-color-surface, #fff); }
  .pt__find { display: flex; gap: 8px; align-items: center; height: 34px; padding: 0 10px; border: 1px solid var(--b2s-color-border-soft, #e1e4ea); border-radius: 9px;
    color: var(--b2s-color-text-muted); font-size: 13px; }
  .pt__find input { flex: 1; min-width: 0; border: 0; outline: 0; background: none; font: inherit; color: var(--b2s-color-text); }
  .pt__rows { display: grid; gap: 1px; }
  .pt__row { display: flex; gap: 6px; align-items: center; min-height: 32px; padding-right: 8px; border: 0; border-radius: 8px; background: none; font: inherit;
    font-size: 13.5px; text-align: left; color: var(--b2s-color-text); cursor: pointer; }
  .pt__row:hover { background: var(--b2s-color-surface-soft, #f6f7f9); }
  .pt__row.is-all, .pt__row.is-zone { font-weight: 600; }
  .pt__row.is-on { background: #0e1218; color: #fff; }
  .pt__row.is-on small { color: #b9bfca; }
  .pt__row i { color: var(--b2s-color-text-faint, #8b93a3); }
  .pt__row.is-on i { color: #fff; }
  .pt__car { width: 10px; flex: none; font-size: 10px; color: var(--b2s-color-text-faint, #8b93a3); }
  .pt__label { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .pt__row small { flex: none; color: var(--b2s-color-text-muted); font-size: 12px; font-weight: 400; }
  .pt__note { margin: 6px 4px; color: var(--b2s-color-text-muted); font-size: 13px; }
</style>
