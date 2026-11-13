<script lang="ts">
  import { onMount } from 'svelte';
  import { page } from '$app/stores';
  import { t } from '$lib/i18n';
  import { apiGetData, apiPostData } from '$lib/api/client';
  import { toast } from '$lib/stores/toast';
  import { reportUiError } from '$lib/errors';
  import { formatBytes, formatDateTime } from '$lib/utils/format';
  import { csvFilename, downloadCsv } from '$lib/utils/csv';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';

  /** Report of the last measure of one folder: duplicates, types, heaviest folders, old files, clutter. */
  type Stats = {
    bytes?: number; files?: number; folders?: number; scanned_at?: string | null; elapsed_ms?: number; mode?: string; last_modified?: string | null;
    top?: Array<{ name: string; bytes: number; files: number }>;
    types?: Array<{ ext: string; files: number; bytes?: number }>;
    cold?: Record<string, { bytes: number; files: number }>;
    cold_top?: Array<{ path: string; bytes: number; modified?: string | null }>;
    junk?: { bytes: number; files: number; examples?: string[] };
    duplicates?: { groups: number; files: number; wasted_bytes: number; truncated?: boolean; top?: Array<{ size: number; files: number; wasted: number; paths: string[] }> };
  };

  let name = '';
  let path = '';
  let stats: Stats | null = null;
  let loading = true;
  let error: string | null = null;
  // Old files: the threshold chosen in the table (the measure keeps 1 year and 3 years)
  let coldSpan: '1y' | '3y' = '1y';
  // Inventory of the 5S module: the biggest files (path, size, last change) and the identical ones among them
  type InvFile = { path: string; size: number; modified: string | null };
  type Group = { size: number; files: number; wasted: number; paths: string[] };
  let invFiles: InvFile[] = [];
  let invDuplicates: Group[] = [];
  let fileQuery = '';
  let showFiles = 50;
  let showGroups = 30;
  // Free threshold on the files of the inventory
  let ageValue = 12;
  let ageUnit: 'months' | 'years' = 'months';

  $: rootId = Number($page.params.id);
  // The measures kept for the folder: the current one and up to 3 previous ones (a bad one can be undone)
  type MeasureLine = { at: string | null; bytes: number | null; files: number | null; wasted: number | null; mode: string | null };
  let measures: { current: MeasureLine | null; previous: MeasureLine[] } = { current: null, previous: [] };
  let restoring = -1;
  const loadMeasures = async () => {
    measures = (await apiGetData<typeof measures>(fetch, `/storage-roots/${rootId}/measures`).catch(() => null)) ?? measures;
  };
  async function restore(index: number) {
    restoring = index;
    try {
      await apiPostData(fetch, `/storage-roots/${rootId}/measures/restore`, { index });
      toast.success(t('Previous measure restored.'));
      location.reload();
    } catch (error: unknown) {
      reportUiError(error, t('Unable to restore this measure.'), 'fives.measures.restore');
    } finally {
      restoring = -1;
    }
  }

  onMount(async () => {
    void loadMeasures();
    try {
      const overview = await apiGetData<Record<string, any>>(fetch, `/storage-roots/${rootId}/overview`);
      name = String(overview?.storage_root_name ?? overview?.name ?? `#${rootId}`);
      path = String(overview?.root_path ?? '');
      stats = (overview?.content as Stats) ?? null;
      const inventory = await apiGetData<{ files: InvFile[]; duplicates: Group[] }>(fetch, `/modules/fives/storage-roots/${rootId}/files`).catch(() => null);
      invFiles = inventory?.files ?? [];
      invDuplicates = inventory?.duplicates ?? [];
    } catch {
      error = t('Unable to load the report of this folder.');
    } finally {
      loading = false;
    }
  });

  const share = (part: number, whole: number) => (whole ? Math.round((part / whole) * 100) : 0);
  $: total = Number(stats?.bytes ?? 0);
  $: cold = stats?.cold?.[coldSpan] ?? null;
  $: duplicates = stats?.duplicates ?? null;
  $: maxType = Math.max(1, ...(stats?.types ?? []).map((item) => item.bytes ?? item.files));
  // Every group found: by the measure (also the smaller files) and in the inventory (the biggest ones), once each
  $: allGroups = (() => {
    const seen = new Map<string, Group>();
    for (const group of [...(duplicates?.top ?? []), ...invDuplicates]) {
      const key = `${group.size}|${[...group.paths].sort()[0] ?? ''}`;
      const known = seen.get(key);
      if (!known || group.paths.length > known.paths.length) seen.set(key, group);
    }
    return [...seen.values()].sort((a, b) => b.wasted - a.wasted);
  })();
  $: shownFiles = invFiles.filter((file) => !fileQuery.trim() || file.path.toLowerCase().includes(fileQuery.trim().toLowerCase()));
  $: cutoff = (() => {
    const date = new Date();
    if (ageUnit === 'years') date.setFullYear(date.getFullYear() - Math.max(0, Number(ageValue) || 0));
    else date.setMonth(date.getMonth() - Math.max(0, Number(ageValue) || 0));
    return date.getTime();
  })();
  $: oldFiles = invFiles.filter((file) => file.modified && new Date(file.modified).getTime() < cutoff);
  $: oldBytes = oldFiles.reduce((sum, file) => sum + file.size, 0);
  const exportFiles = (rows: InvFile[], label: string) =>
    downloadCsv(csvFilename(`${label}-${name}`), [
      { header: t('Path'), value: (row: InvFile) => row.path },
      { header: t('Size'), value: (row: InvFile) => row.size },
      { header: t('Last change'), value: (row: InvFile) => row.modified ?? '' }
    ], rows);

  const exportDuplicates = () =>
    downloadCsv(csvFilename(`doublons-${name}`), [
      { header: t('Size'), value: (row: any) => row.size },
      { header: t('Copies'), value: (row: any) => row.files },
      { header: t('Space lost'), value: (row: any) => row.wasted },
      { header: t('Paths'), value: (row: any) => (row.paths ?? []).join(' | ') }
    ], allGroups);
</script>

<div class="rp">
  <a class="b2s-btn b2s-btn-sm b2s-btn-secondary" href="/five-s"><i class="bi bi-arrow-left" aria-hidden="true"></i>{t('All the folders')}</a>
  {#if loading}
    <LoadingState skeleton="page" rows={6} />
  {:else if error}
    <InlineAlert tone="error">{error}</InlineAlert>
  {:else if !stats}
    <InlineAlert tone="info">{t('This folder was never measured: measure it from its page, the report appears here afterwards.')}</InlineAlert>
  {:else}
    <header class="rp__head">
      <h1>{t('Report · {name}', { name })}</h1>
      <p><code>{path}</code> · {t('measured {when}', { when: formatDateTime(stats.scanned_at) })}{stats.elapsed_ms ? ` · ${Math.round(stats.elapsed_ms / 60000)} min` : ''}
        · <a href={`/storage-roots?selected=${rootId}`}>{t('Open the folder')}</a></p>
    </header>

    {#if measures.previous.length}
      <section class="rp__card rp__measures" aria-label={t('Measures')}>
        <header><h2>{t('Measures')}</h2><small>{t('The current one and the previous ones kept: go back to one if the last measure is wrong.')}</small></header>
        <table class="b2s-table">
          <thead><tr><th>{t('Date')}</th><th class="rp__num">{t('Volume')}</th><th class="rp__num">{t('Files')}</th><th class="rp__num">{t('Lost to duplicates')}</th><th></th></tr></thead>
          <tbody>
            {#if measures.current}<tr class="is-current"><td>{measures.current.at ? formatDateTime(measures.current.at) : '—'} · <b>{t('current')}</b></td><td class="rp__num">{formatBytes(measures.current.bytes ?? 0)}</td><td class="rp__num">{(measures.current.files ?? 0).toLocaleString('fr-FR')}</td><td class="rp__num">{formatBytes(measures.current.wasted ?? 0)}</td><td></td></tr>{/if}
            {#each measures.previous as item, index (index)}
              <tr><td>{item.at ? formatDateTime(item.at) : '—'}</td><td class="rp__num">{formatBytes(item.bytes ?? 0)}</td><td class="rp__num">{(item.files ?? 0).toLocaleString('fr-FR')}</td><td class="rp__num">{formatBytes(item.wasted ?? 0)}</td>
                <td><button type="button" class="b2s-btn b2s-btn-sm b2s-btn-secondary" disabled={restoring >= 0} on:click={() => restore(index)}>{t('Go back to this measure')}</button></td></tr>
            {/each}
          </tbody>
        </table>
      </section>
    {/if}

    <section class="rp__kpis">
      <div><span>{t('Volume')}</span><b>{formatBytes(stats.bytes)}</b></div>
      <div><span>{t('Files')}</span><b>{Number(stats.files ?? 0).toLocaleString('fr-FR')}</b></div>
      <div><span>{t('Sub-folders')}</span><b>{Number(stats.folders ?? 0).toLocaleString('fr-FR')}</b></div>
      <div class:is-warn={(duplicates?.wasted_bytes ?? 0) > 0}><span>{t('Lost to duplicates')}</span><b>{formatBytes(duplicates?.wasted_bytes ?? 0)}</b>
        <small>{t('{groups} group(s), {files} file(s)', { groups: (duplicates?.groups ?? 0).toLocaleString('fr-FR'), files: (duplicates?.files ?? 0).toLocaleString('fr-FR') })}</small></div>
      <div><span>{t('Not modified for 1 year')}</span><b>{formatBytes(stats.cold?.['1y']?.bytes ?? 0)}</b><small>{share(stats.cold?.['1y']?.bytes ?? 0, total)} %</small></div>
      <div><span>{t('Clutter')}</span><b>{formatBytes(stats.junk?.bytes ?? 0)}</b><small>{t('{count} file(s)', { count: stats.junk?.files ?? 0 })}</small></div>
    </section>

    <div class="rp__grid">
      <section class="rp__card rp__wide">
        <header><h2>{t('Duplicates')} <a class="rp__more" href={`/five-s/duplicates/${rootId}`}>{t('Decide copy by copy')} ›</a></h2>
          <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-secondary" disabled={!allGroups.length} on:click={exportDuplicates}><i class="bi bi-download" aria-hidden="true"></i>{t('Export CSV')}</button></header>
        <p class="rp__hint">{t('The biggest groups of identical files (same content); the copies beyond the first are space lost.')}{duplicates?.truncated ? ` ${t('Only part of the files could be compared.')}` : ''}</p>
        <table class="b2s-table">
          <thead><tr><th>{t('Size')}</th><th>{t('Copies')}</th><th>{t('Space lost')}</th><th>{t('Where')}</th></tr></thead>
          <tbody>
            {#each allGroups.slice(0, showGroups) as group}
              <tr><td>{formatBytes(group.size)}</td><td>{group.files}</td><td><b>{formatBytes(group.wasted)}</b></td>
                <td class="rp__paths">{#each group.paths as file}<code title={file}>{file}</code>{/each}{#if group.files > group.paths.length}<small>{t('and {count} more', { count: group.files - group.paths.length })}</small>{/if}</td></tr>
            {:else}<tr><td colspan="4">{t('No duplicate found.')}</td></tr>{/each}
          </tbody>
        </table>
        {#if allGroups.length > showGroups}<button type="button" class="b2s-link-btn" on:click={() => (showGroups += 50)}>{t('Show more ({count} groups in all)', { count: allGroups.length })}</button>{/if}
      </section>

      <section class="rp__card">
        <header><h2>{t('Heaviest sub-folders')}</h2></header>
        <table class="b2s-table">
          <thead><tr><th>{t('Sub-folder')}</th><th class="rp__num">{t('Volume')}</th><th class="rp__num">{t('Files')}</th></tr></thead>
          <tbody>{#each stats.top ?? [] as item}
            <tr><td><span class="rp__bar" style={`--w:${share(item.bytes, total)}%`}></span>{item.name}</td><td class="rp__num">{formatBytes(item.bytes)} <small>{share(item.bytes, total)} %</small></td><td class="rp__num">{item.files.toLocaleString('fr-FR')}</td></tr>
          {/each}</tbody>
        </table>
      </section>

      <section class="rp__card">
        <header><h2>{t('File types')}</h2></header>
        <table class="b2s-table">
          <thead><tr><th>{t('Extension')}</th><th class="rp__num">{t('Volume')}</th><th class="rp__num">{t('Files')}</th></tr></thead>
          <tbody>{#each stats.types ?? [] as item}
            <tr><td><span class="rp__bar" style={`--w:${Math.round(((item.bytes ?? item.files) / maxType) * 100)}%`}></span><code>.{item.ext || '—'}</code></td>
              <td class="rp__num">{item.bytes != null ? formatBytes(item.bytes) : '—'}</td><td class="rp__num">{item.files.toLocaleString('fr-FR')}</td></tr>
          {/each}</tbody>
        </table>
        {#if (stats.types ?? []).some((item) => item.bytes == null)}<small class="rp__hint">{t('Measure the folder again to see the volume of each type.')}</small>{/if}
      </section>

      <section class="rp__card">
        <header><h2>{t('Old files')}</h2>
          <select class="b2s-select" bind:value={coldSpan} aria-label={t('Not modified for')}>
            <option value="1y">{t('more than 1 year')}</option>
            <option value="3y">{t('more than 3 years')}</option>
          </select></header>
        <p class="rp__big">{formatBytes(cold?.bytes ?? 0)} <small>{t('{files} file(s) · {share} % of the folder', { files: (cold?.files ?? 0).toLocaleString('fr-FR'), share: share(cold?.bytes ?? 0, total) })}</small></p>
        <h3>{t('The biggest old files')}</h3>
        <ul class="rp__list">{#each stats.cold_top ?? [] as file}
          <li><code title={file.path} data-copy={file.path}>{file.path}</code><span>{formatBytes(file.bytes)}{file.modified ? ` · ${formatDateTime(file.modified)}` : ''}</span></li>
        {/each}</ul>
        <small class="rp__hint">{t('Based on the date of last modification (Windows rarely keeps the date of last access).')}</small>
      </section>

      <section class="rp__card rp__wide">
        <header><h2>{t('Biggest files')}</h2>
          <div class="rp__tools">
            <input class="b2s-input" placeholder={t('Filter by path…')} bind:value={fileQuery} aria-label={t('Filter by path')} />
            <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-secondary" disabled={!shownFiles.length} on:click={() => exportFiles(shownFiles, 'gros-fichiers')}><i class="bi bi-download" aria-hidden="true"></i>{t('Export CSV')}</button>
          </div></header>
        {#if !invFiles.length}<p class="rp__hint">{t('No file in the inventory of the 5S module yet: measure the folder with the module on.')}</p>{:else}
        <table class="b2s-table">
          <thead><tr><th>{t('Path')}</th><th class="rp__num">{t('Size')}</th><th class="rp__num">{t('Last change')}</th></tr></thead>
          <tbody>{#each shownFiles.slice(0, showFiles) as file}
            <tr><td class="rp__path"><code title={file.path} data-copy={file.path}>{file.path}</code></td><td class="rp__num">{formatBytes(file.size)}</td><td class="rp__num">{file.modified ? formatDateTime(file.modified) : '—'}</td></tr>
          {/each}</tbody>
        </table>
        {#if shownFiles.length > showFiles}<button type="button" class="b2s-link-btn" on:click={() => (showFiles += 100)}>{t('Show more ({count} files)', { count: shownFiles.length })}</button>{/if}
        <small class="rp__hint">{t('The {count} biggest files kept by the inventory (files of 1 MB and more).', { count: invFiles.length.toLocaleString('fr-FR') })}</small>{/if}
      </section>

      <section class="rp__card rp__wide">
        <header><h2>{t('Files not modified for…')}</h2>
          <div class="rp__tools">
            <input class="b2s-input rp__age" type="number" min="0" bind:value={ageValue} aria-label={t('Age')} />
            <select class="b2s-select" bind:value={ageUnit} aria-label={t('Unit')}><option value="months">{t('months')}</option><option value="years">{t('years')}</option></select>
            <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-secondary" disabled={!oldFiles.length} on:click={() => exportFiles(oldFiles, 'fichiers-anciens')}><i class="bi bi-download" aria-hidden="true"></i>{t('Export CSV')}</button>
          </div></header>
        <p class="rp__big">{formatBytes(oldBytes)} <small>{t('{count} of the {total} biggest files', { count: oldFiles.length.toLocaleString('fr-FR'), total: invFiles.length.toLocaleString('fr-FR') })}</small></p>
        <ul class="rp__list">{#each oldFiles.slice(0, 15) as file}
          <li><code title={file.path} data-copy={file.path}>{file.path}</code><span>{formatBytes(file.size)} · {file.modified ? formatDateTime(file.modified) : '—'}</span></li>
        {/each}</ul>
      </section>

      <section class="rp__card">
        <header><h2>{t('Clutter')}</h2></header>
        <p class="rp__big">{formatBytes(stats.junk?.bytes ?? 0)} <small>{t('{count} file(s): copies, temporary and system files', { count: stats.junk?.files ?? 0 })}</small></p>
        <ul class="rp__list">{#each stats.junk?.examples ?? [] as file}<li><code title={file}>{file}</code></li>{/each}</ul>
      </section>
    </div>
  {/if}
</div>

<style>
  .rp { display: grid; grid-template-columns: minmax(0, 1fr); gap: 16px; min-width: 0; padding: var(--b2s-page-padding); }
  .rp__head h1 { margin: 0 0 4px; font-size: 24px; }
  .rp__head p { margin: 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .rp__kpis { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 12px; }
  .rp__kpis > div { display: grid; gap: 2px; padding: 14px 16px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-md, 10px); background: var(--b2s-color-surface, #fff); }
  .rp__kpis span, .rp__kpis small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .rp__kpis b { font-size: 20px; }
  .rp__kpis .is-warn b { color: var(--b2s-color-warning-strong, #b54708); }
  .rp__grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
  .rp__card { padding: 16px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-md, 10px); background: var(--b2s-color-surface, #fff); min-width: 0; }
  .rp__wide { grid-column: 1 / -1; }
  .rp__card > header { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 8px; }
  .rp__card h2 { margin: 0; font-size: 16px; }
  .rp__card h3 { margin: 12px 0 6px; font-size: var(--b2s-fs-sm); color: var(--b2s-color-text-muted); }
  .rp__hint { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .rp__num { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }
  .rp__num small { color: var(--b2s-color-text-muted); }
  .rp__bar { display: block; height: 3px; width: var(--w); max-width: 100%; margin-bottom: 4px; border-radius: 2px; background: var(--b2s-color-info-strong, #2563eb); }
  .rp__paths { display: grid; gap: 2px; max-width: 640px; }
  .rp__paths code, .rp__list code { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: var(--b2s-fs-xs); }
  .rp__tools { display: flex; gap: 6px; align-items: center; }
  .rp__tools .b2s-input { width: 220px; }
  .rp__tools .rp__age { width: 80px; }
  .rp__path { max-width: 720px; }
  .rp__path code { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: var(--b2s-fs-xs); }
  .rp__measures header { display: grid; gap: 2px; margin-bottom: 8px; }
  .rp__measures header small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .rp__measures tr.is-current td { background: #F5FBE6; }
  .rp__big { margin: 0; font-size: 22px; font-weight: 600; }
  .rp__big small { display: block; font-size: var(--b2s-fs-xs); font-weight: 400; color: var(--b2s-color-text-muted); }
  .rp__list { display: grid; gap: 4px; margin: 0; padding: 0; list-style: none; }
  .rp__list li { display: flex; justify-content: space-between; gap: 12px; min-width: 0; font-size: var(--b2s-fs-sm); }
  .rp__list span { white-space: nowrap; color: var(--b2s-color-text-muted); }
</style>
