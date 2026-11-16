<script lang="ts">
  import { t } from '$lib/i18n';
  import { apiGetData } from '$lib/api/client';
  import { formatBytes, formatDate } from '$lib/utils/format';
  import { csvFilename, downloadCsv } from '$lib/utils/csv';
  import { reportUiError } from '$lib/errors';

  /**
   * Files of the inventory (last measure) by name, extension, owner, size and age: in one governed folder, or in
   * every folder the person may see. The biggest first.
   */
  interface Props {
    rootId?: number | null;
    /** Opens a result (the folder of the file in the explorer) */
    onOpen?: (file: Hit) => void;
  }

  type Hit = { storage_root_id: number; folder_name: string | null; path: string; name: string; size: number; modified: string | null;
    created: string | null; accessed: string | null; extension: string | null; owner: string | null };

  let { rootId = null, onOpen }: Props = $props();
  let q = $state('');
  let ext = $state('');
  let owner = $state('');
  let minMb = $state<number | null>(null);
  let olderYears = $state<number | null>(null);
  let more = $state(false);
  let hits = $state<Hit[] | null>(null);
  let total = $state(0);
  let bytes = $state(0);
  let busy = $state(false);

  let any = $derived(Boolean(q.trim() || ext.trim() || owner.trim() || minMb || olderYears));

  async function search() {
    if (!any || busy) return;
    busy = true;
    try {
      const params: Record<string, string> = {};
      if (rootId) params.root_id = String(rootId);
      if (q.trim()) params.q = q.trim();
      if (ext.trim()) params.ext = ext.trim();
      if (owner.trim()) params.owner = owner.trim();
      if (minMb) params.min_bytes = String(Math.round(minMb * 1024 * 1024));
      if (olderYears) params.older_days = String(Math.round(olderYears * 365));
      params.limit = '300';
      const data = await apiGetData<{ files: Hit[]; total: number; bytes: number }>(fetch, '/modules/fives/files/search', params);
      hits = data?.files ?? [];
      total = data?.total ?? 0;
      bytes = data?.bytes ?? 0;
    } catch (failure) {
      reportUiError(failure, t('Unable to search the files.'), 'fives.files.search');
    } finally {
      busy = false;
    }
  }
  function clear() {
    q = ext = owner = '';
    minMb = olderYears = null;
    hits = null;
  }
  const exportHits = () => downloadCsv(csvFilename('fichiers'), [
    ...(rootId ? [] : [{ header: t('Governed folder'), value: (row: Hit) => row.folder_name ?? '' }]),
    { header: t('Path'), value: (row: Hit) => row.path }, { header: t('Size'), value: (row: Hit) => row.size },
    { header: t('Last change'), value: (row: Hit) => row.modified ?? '' }, { header: t('Created'), value: (row: Hit) => row.created ?? '' },
    { header: t('Last access'), value: (row: Hit) => row.accessed ?? '' }, { header: t('NTFS owner'), value: (row: Hit) => row.owner ?? '' }
  ], hits ?? []);
</script>

<form class="fs5" onsubmit={(event) => { event.preventDefault(); void search(); }}>
  <label class="v2-search fs5__q"><i class="bi bi-search" aria-hidden="true"></i>
    <input type="search" bind:value={q} placeholder={rootId ? t('Find a file in this folder…') : t('Find a file in every folder…')} aria-label={t('Find a file')} /></label>
  <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-ghost" onclick={() => (more = !more)} aria-expanded={more}><i class="bi bi-sliders" aria-hidden="true"></i>{t('Filters')}</button>
  <button type="submit" class="b2s-btn b2s-btn-sm b2s-btn-primary" disabled={!any || busy}>{t('Search')}</button>
  {#if hits}<button type="button" class="b2s-btn b2s-btn-sm b2s-btn-ghost" onclick={clear}>{t('Clear')}</button>{/if}
  {#if more}
    <div class="fs5__more">
      <label>{t('Extension')}<input class="b2s-input" bind:value={ext} placeholder="pdf" /></label>
      <label>{t('NTFS owner')}<input class="b2s-input" bind:value={owner} placeholder="CORP\jane" /></label>
      <label>{t('At least (MB)')}<input class="b2s-input" type="number" min="0" bind:value={minMb} /></label>
      <label>{t('Not modified for (years)')}<input class="b2s-input" type="number" min="0" step="0.5" bind:value={olderYears} /></label>
    </div>
  {/if}
</form>

{#if hits}
  <div class="v2-sec fs5__res">
    <div class="v2-sh"><span>{t('{count} file(s), {size}', { count: total.toLocaleString('fr-FR'), size: formatBytes(bytes) })}{total > hits.length ? ` · ${t('the {count} biggest shown', { count: hits.length })}` : ''}</span>
      <div class="v2-sh__r"><button type="button" class="b2s-btn b2s-btn-sm b2s-btn-secondary" disabled={!hits.length} onclick={exportHits}><i class="bi bi-download" aria-hidden="true"></i>{t('Export CSV')}</button></div></div>
    <div class="v2-list">
      {#each hits as hit (hit.storage_root_id + hit.path)}
        <button type="button" class="v2-row fs5__row" class:has-root={!rootId} onclick={() => onOpen?.(hit)}>
          <span class="v2-nm"><span><i class="bi bi-file-earmark" aria-hidden="true"></i> {hit.name}</span><code class="v2-sub">{hit.path}</code></span>
          {#if !rootId}<span class="v2-sub">{hit.folder_name ?? `#${hit.storage_root_id}`}</span>{/if}
          <span>{formatBytes(hit.size)}</span>
          <span class="v2-sub">{hit.modified ? formatDate(hit.modified) : '—'}</span>
          <span class="v2-sub fs5__owner">{hit.owner ?? ''}</span>
        </button>
      {:else}
        <p class="v2-empty">{t('No file matches in the last measure.')}</p>
      {/each}
    </div>
  </div>
{/if}

<style>
  .fs5 { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
  .fs5__q { flex: 1 1 320px; }
  .fs5__more { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; width: 100%; }
  .fs5__more label { display: grid; gap: 4px; font-size: var(--b2s-fs-xs); color: var(--b2s-color-text-muted); }
  .fs5__res { margin-top: 4px; }
  .fs5__row { grid-template-columns: minmax(240px, 2fr) 100px 110px minmax(120px, 1fr); width: 100%; border: 0; background: none; font: inherit; text-align: left; cursor: pointer; }
  .fs5__row.has-root { grid-template-columns: minmax(240px, 2fr) minmax(120px, 1fr) 100px 110px minmax(120px, 1fr); }
  .fs5__row code, .fs5__owner { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
