<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { t } from '$lib/i18n';
  import { apiGetData } from '$lib/api/client';
  import { formatBytes } from '$lib/utils/format';
  import { csvFilename, downloadCsv } from '$lib/utils/csv';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import FolderHeader from '../../FolderHeader.svelte';
  import AccessPanel from '../../AccessPanel.svelte';
  import { goto } from '$app/navigation';
  import { toast } from '$lib/stores/toast';
  import { copyText } from '$lib/utils/clipboard';
  import { readParam, writeParams } from '$lib/utils/url-state';
  import ContextMenu, { menuPositionFor, type ContextMenuItem } from '$lib/components/ui/ContextMenu.svelte';

  /**
   * Rights to review in the whole tree of a governed folder: every sub-folder with an orphan SID, the whole company
   * allowed to write, full control or accounts set by hand, or a broken inheritance. Choose one: who reaches it and why.
   */
  type Row = { path: string; name: string; depth: number; bytes: number; files: number; codes: string[] };
  type Review = { folders: Row[]; total: number; counts: Record<string, number>; folders_read: number; folders_measured: number };

  let rootId = $derived(Number($page.params.id));
  let name = $state('');
  let rootPath = $state('');
  let data = $state<Review | null>(null);
  let loading = $state(true);
  let error = $state<string | null>(null);
  let code = $state<string>(readParam<string>('code', 'all'));
  const askedPath = readParam<string>('path', '');
  let query = $state('');
  let chosen = $state<Row | null>(null);
  let shown = $state(100);

  const LABEL = (): Record<string, string> => ({
    ORPHAN_SID: t('Orphan SID'), BROAD_WRITE: t('Whole company writing'), FULL_CONTROL: t('Full control'),
    EXPLICIT_ENTRY: t('Rights set by hand'), INHERITANCE_BROKEN: t('Broken inheritance')
  });
  const TONE: Record<string, string> = { ORPHAN_SID: 'bad', BROAD_WRITE: 'bad', FULL_CONTROL: 'warn', EXPLICIT_ENTRY: 'warn', INHERITANCE_BROKEN: 'info' };
  const ORDER = ['ORPHAN_SID', 'BROAD_WRITE', 'FULL_CONTROL', 'EXPLICIT_ENTRY', 'INHERITANCE_BROKEN'];

  onMount(async () => {
    try {
      const overview = await apiGetData<Record<string, any>>(fetch, `/storage-roots/${rootId}/overview`);
      name = String(overview?.storage_root_name ?? `#${rootId}`);
      rootPath = String(overview?.root_path ?? '');
      data = await apiGetData<Review>(fetch, `/modules/fives/storage-roots/${rootId}/rights-review`);
      if (askedPath) chosen = data?.folders.find((row) => row.path.toLowerCase() === askedPath.toLowerCase()) ?? null;
    } catch {
      error = t('Unable to load the rights of this folder.');
    } finally {
      loading = false;
    }
  });

  $effect(() => writeParams({ code: code === 'all' ? null : code, path: chosen?.path ?? null }));
  let menu = $state<{ row: Row; at: { x: number; y: number } } | null>(null);
  const menuItems = (): ContextMenuItem[] => [
    { key: 'why', label: t('Who has access and why'), icon: 'bi-people' },
    { key: 'explore', label: t('Open in the explorer'), icon: 'bi-columns-gap' },
    { key: 'copy', label: t('Copy the path'), icon: 'bi-clipboard', separated: true }
  ];
  async function pick(key: string) {
    const row = menu?.row;
    menu = null;
    if (!row) return;
    if (key === 'why') chosen = row;
    else if (key === 'explore') await goto(`/five-s/explore/${rootId}?open=${encodeURIComponent(row.path)}`);
    else if (await copyText(row.path)) toast.success(t('Path copied.'));
  }
  let rows = $derived((data?.folders ?? []).filter((row) => (code === 'all' || row.codes.includes(code))
    && (!query.trim() || row.path.toLowerCase().includes(query.trim().toLowerCase()))));
  const exportRows = () => downloadCsv(csvFilename(`droits-a-revoir-${name}`), [
    { header: t('Folder'), value: (row: Row) => row.path },
    { header: t('To review'), value: (row: Row) => row.codes.map((item) => LABEL()[item] ?? item).join(' | ') },
    { header: t('Files'), value: (row: Row) => row.files },
    { header: t('Volume'), value: (row: Row) => row.bytes }
  ], rows);
</script>

<section class="v2 ar5">
  <FolderHeader {rootId} {name} path={rootPath} current="access" counts={{ access: data?.total ?? 0 }}>
    {#snippet actions()}
      <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-secondary" disabled={!rows.length} onclick={exportRows}><i class="bi bi-download" aria-hidden="true"></i>{t('Export CSV')}</button>
    {/snippet}
  </FolderHeader>

  {#if loading}
    <LoadingState skeleton="page" rows={6} />
  {:else if error}
    <InlineAlert tone="error">{error}</InlineAlert>
  {:else if data && !data.folders_read}
    <InlineAlert tone="info">{t('The rights of the sub-folders are read at the next full measure of this folder.')}</InlineAlert>
  {:else if data}
    <p class="ar5__lede">{t('A first screen from the rights of the last measure ({read} folder(s) read): choose a folder to see who reaches it and why, resolved with the directory.', { read: data.folders_read })}</p>
    <div class="v2-seg" role="group" aria-label={t('To review')}>
      <button type="button" class:is-on={code === 'all'} onclick={() => (code = 'all')}>{t('All')} <b>{data.total}</b></button>
      {#each ORDER as item (item)}
        {#if data.counts[item]}<button type="button" class:is-on={code === item} onclick={() => (code = item)}>{LABEL()[item]} <b>{data.counts[item]}</b></button>{/if}
      {/each}
    </div>
    <div class="ar5__body">
      <div class="v2-sec">
        <div class="v2-sh"><label class="v2-search"><i class="bi bi-search" aria-hidden="true"></i><input type="search" bind:value={query} placeholder={t('Folder, path…')} aria-label={t('Search a folder')} /></label></div>
        <div class="v2-list">
          {#each rows.slice(0, shown) as row (row.path)}
            <button type="button" class="v2-row ar5__row" class:is-sel={chosen?.path === row.path} onclick={() => (chosen = row)}
              oncontextmenu={(event) => { event.preventDefault(); menu = { row, at: menuPositionFor(event) }; }}>
              <span class="v2-nm"><span><i class="bi bi-folder" aria-hidden="true"></i> {row.name}</span><code class="v2-sub">{row.path}</code></span>
              <span class="ar5__tags">{#each row.codes as item (item)}<span class={`v2-tag is-${TONE[item] ?? 'mut'}`}>{LABEL()[item] ?? item}</span>{/each}</span>
              <span class="v2-sub">{formatBytes(row.bytes)}</span>
            </button>
          {:else}
            <p class="v2-empty">{data.total ? t('No folder matches.') : t('Nothing to review: no orphan SID, no folder open in writing to everyone, no right set by hand.')}</p>
          {/each}
        </div>
        {#if rows.length > shown}<button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" onclick={() => (shown += 100)}>{t('Show {count} more', { count: Math.min(100, rows.length - shown) })}</button>{/if}
      </div>
      <aside class="v2-sec ar5__side" aria-label={t('Who has access and why')}>
        {#if chosen}
          <h2>{chosen.name}</h2>
          <AccessPanel {rootId} path={chosen.path} />
          <a class="b2s-link-btn" href={`/five-s/explore/${rootId}?open=${encodeURIComponent(chosen.path)}`}>{t('Open in the explorer')} ›</a>
        {:else}
          <p class="v2-empty">{t('Choose a folder to see who reaches it and why.')}</p>
        {/if}
      </aside>
    </div>
  {/if}
</section>

<ContextMenu open={Boolean(menu)} title={menu?.row.name ?? ''} subtitle={menu?.row.path ?? ''} items={menu ? menuItems() : []}
  at={menu?.at ?? { x: 0, y: 0 }} onClose={() => (menu = null)} onPick={(key) => void pick(key)} />

<style>
  .ar5 { display: grid; gap: 14px; padding: var(--b2s-page-padding); }
  .ar5__lede { margin: 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .ar5__body { display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(320px, 1fr); gap: 16px; align-items: start; }
  .ar5__row { grid-template-columns: minmax(200px, 1.2fr) minmax(200px, 1.4fr) 90px; width: 100%; border: 0; background: none; font: inherit; text-align: left; cursor: pointer; }
  .ar5__row.is-sel { background: var(--b2s-accent-soft); }
  .ar5__row code { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .ar5__tags { display: flex; flex-wrap: wrap; gap: 4px; }
  .ar5__side { position: sticky; top: calc(var(--b2s-shell-top) + 12px); display: grid; gap: 10px; }
  .ar5__side h2 { margin: 0; font-size: 18px; }
</style>
