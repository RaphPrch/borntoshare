<script lang="ts">
  

  import { onDestroy } from 'svelte';
  import { apiGetData, apiPostData } from '$lib/api/client';
  import { reportUiError } from '$lib/errors';
  import { flashOn } from '$lib/utils/motion';
  import { fivesEnabled } from '$lib/utils/features';
  import { t } from '$lib/i18n';
  import { formatBytes, formatDateTime, timeAgo } from '$lib/utils/format';
  import CountUp from '$lib/components/ui/CountUp.svelte';
  import StorageRootGrowth from '$lib/components/storage-roots/StorageRootGrowth.svelte';

  /**
   * Content of a governed folder, as its last measure found it: size, sub-folders and files, where the weight is,
   * which file types, how old the data is, clutter and duplicates. The measure is its own job (apart from the test
   * of the folder), walked on the Windows server when it can. One hue, bars with their value written.
   */
  type Content = {
    bytes?: number | null;
    files?: number;
    folders?: number;
    truncated?: boolean;
    scanned_at?: string | null;
    top?: Array<{ name: string; bytes: number; files: number }>;
    types?: Array<{ ext: string; files: number }>;
    cold?: { '1y': { bytes: number; files: number }; '3y': { bytes: number; files: number } };
    cold_top?: Array<{ path: string; bytes: number; modified: string }>;
    junk?: { bytes: number; files: number; examples: string[] };
    last_modified?: string | null;
    method?: 'server' | 'smb' | 'derived';
    mode?: 'full' | 'incremental';
    elapsed_ms?: number;
    denied_folders?: number;
    duplicates?: { groups: number; files: number; wasted_bytes: number; truncated: boolean;
      top: Array<{ size: number; files: number; wasted: number; paths: string[] }> };
  };
  type Scan = { status: 'running' | 'done' | 'failed'; method: string | null; fallback_reason: string | null; requested_at: string | null;
    finished_at: string | null; elapsed_ms: number | null; files: number | null; error: string | null; mode?: string | null;
    progress?: { mode: string; chunks_total: number; chunks_done: number; chunks_kept: number; files: number; current: string | null } | null };
  type Shared = { files: number; bytes: number; with: number[]; examples: Array<{ path: string; size: number; also_in: string[] }> };
  
  interface Props {
    content?: Content | null;
    rootId?: number | null;
    isAdmin?: boolean;
    /** A measure landed: the page reads the folder again */
    onMeasured?: () => void;
  }

  let {
    content = null,
    rootId = null,
    isAdmin = false,
    onMeasured = () => {}
  }: Props = $props();

  let scan: Scan | null = $state(null);
  let shared: Shared | null = $state(null);
  let loadedFor: number | null = $state(null);
  let busy = $state(false);
  let landed = $state(0);
  let timer: ReturnType<typeof setInterval> | null = null;
  async function loadScan() {
    loadedFor = rootId;
    const data = await apiGetData<{ scan: Scan | null }>(fetch, `/storage-roots/${rootId}/scan`).catch(() => null);
    const was = scan?.status;
    scan = data?.scan ?? null;
    // Duplicates with other folders: the 5S module, when it is on
    shared = $fivesEnabled
      ? ((await apiGetData<{ shared: Shared | null }>(fetch, `/modules/fives/storage-roots/${rootId}/duplicates`).catch(() => null))?.shared ?? null)
      : null;
    if (was === 'running' && scan?.status === 'done') {
      landed += 1;
      onMeasured();
    }
  }
  async function stopMeasure() {
    if (!rootId) return;
    try {
      await apiPostData(fetch, `/storage-roots/${rootId}/stop`, { kind: 'measure' });
      await loadScan();
    } catch (error: unknown) {
      reportUiError(error, 'Unable to stop the measure.', 'storage-roots.measure.stop');
    }
  }
  function start() {
    if (!timer) timer = setInterval(() => rootId && loadScan(), 3000);
  }
  function stop() {
    if (timer) clearInterval(timer);
    timer = null;
  }
  onDestroy(stop);
  async function measure() {
    if (!rootId || busy) return;
    busy = true;
    try {
      scan = await apiPostData<Scan>(fetch, `/storage-roots/${rootId}/measure`, {});
    } catch (error: unknown) {
      reportUiError(error, 'Unable to measure the folder.', 'storage-roots.measure');
    } finally {
      busy = false;
    }
  }
  const seconds = (ms: number | null | undefined) => (ms == null ? '' : ms < 1000 ? `${ms} ms` : `${(ms / 1000).toLocaleString('fr-FR', { maximumFractionDigits: 1 })} s`);

  const size = (bytes: number | null | undefined) => formatBytes(bytes);
  const count = (value: number | undefined) => (value == null ? '—' : value.toLocaleString('fr-FR'));
  const pct = (value: number) => (total ? Math.round((value / total) * 100) : 0);
  $effect.pre(() => {
    if (rootId && rootId !== loadedFor) loadScan();
  });
  let measuring = $derived(scan?.status === 'running');
  $effect.pre(() => {
    measuring ? start() : stop();
  });
  let dups = $derived(content?.duplicates ?? null);
  // Empty sub-folders say nothing about where the weight is
  let top = $derived((content?.top ?? []).filter((row) => row.bytes > 0));
  let maxTop = $derived(Math.max(1, ...top.map((row) => row.bytes)));
  let types = $derived(content?.types ?? []);
  let maxType = $derived(Math.max(1, ...types.map((row) => row.files)));
  let floor = $derived(content?.truncated ? '≥ ' : '');
  // Age of the data: under a year, 1 to 3 years, over 3 years (share of the bytes)
  let total = $derived(Number(content?.bytes ?? 0));
  let c1 = $derived(Number(content?.cold?.['1y']?.bytes ?? 0));
  let c3 = $derived(Number(content?.cold?.['3y']?.bytes ?? 0));
  let ages = $derived(content?.cold && total > 0
    ? [
        { key: 'fresh', label: t('Changed this year'), bytes: total - c1 },
        { key: 'cold', label: t('1 to 3 years'), bytes: c1 - c3 },
        { key: 'frozen', label: t('Over 3 years'), bytes: c3 }
      ]
    : []);
</script>

<section class="cc" aria-label={t('Content of the folder')} use:flashOn={landed}>
  <header>
    <h2>{t('Content')}</h2>
    <small>
      {#if measuring}<span class="b2s-spinner b2s-spinner--sm" aria-hidden="true"></span> {scan?.progress ? t('Scan {done}/{total} · {files} file(s)', { done: scan.progress.chunks_done, total: scan.progress.chunks_total, files: scan.progress.files.toLocaleString('fr-FR') }) : t('Measure in progress…')}
      {#if isAdmin}· <button type="button" class="b2s-link-btn" onclick={stopMeasure}>{t('Stop')}</button>{/if}
      {:else if content?.scanned_at}<span title={formatDateTime(content.scanned_at)}>{t('measured {when}', { when: timeAgo(content.scanned_at) })}</span>{#if content.mode === 'incremental'} · {t('incremental')}{/if}{#if content.method} · {content.method === 'derived' ? t('from the measure of the parent folder') : content.method === 'server' ? t('on the server') : t('through SMB')}{content.elapsed_ms != null ? ` (${seconds(content.elapsed_ms)})` : ''}{/if}
      {:else}{t('Not measured yet')}{/if}
      {#if rootId && !measuring} · <button type="button" class="b2s-link-btn" disabled={busy} onclick={measure}>{content?.scanned_at ? t('Measure again') : t('Measure the folder')}</button>{/if}
    </small>
  </header>
  {#if measuring && scan?.progress?.chunks_total}
    <div class="cc__progress" role="progressbar" aria-valuemin={0} aria-valuemax={scan.progress.chunks_total} aria-valuenow={scan.progress.chunks_done}
      aria-label={t('Progress of the scan')}>
      <span style={`width:${Math.round((scan.progress.chunks_done / scan.progress.chunks_total) * 100)}%`}></span>
    </div>
    <small class="cc__note">{scan.progress.mode === 'incremental' ? t('Incremental: only the sub-folders changed since the last scan ({kept} kept as they are)', { kept: scan.progress.chunks_kept }) : t('Full walk')}{scan.progress.current ? ` · ${scan.progress.current}` : ''}
      {#if scan.requested_at} · {t('started {when}', { when: timeAgo(scan.requested_at) })}{/if}</small>
  {/if}
  {#if scan?.status === 'failed'}<p class="cc__fail" role="alert"><i class="bi bi-exclamation-octagon" aria-hidden="true"></i>{t('The last measure failed')}: {scan.error}</p>{/if}
  {#if scan?.fallback_reason && content?.method === 'smb'}<p class="cc__note">{t('Measured through SMB (no duplicates): the server could not be walked on.')} <code>{scan.fallback_reason}</code></p>{/if}
  {#if content}
    <div class="cc__tiles">
      <div class="cc__tile"><i class="bi bi-hdd" aria-hidden="true"></i><span>{t('Size')}</span><b>{floor}<CountUp value={content.bytes} format={(n) => size(Math.round(n))} /></b></div>
      <div class="cc__tile"><i class="bi bi-folder2" aria-hidden="true"></i><span>{t('Sub-folders')}</span><b>{floor}<CountUp value={content.folders} /></b></div>
      <div class="cc__tile"><i class="bi bi-file-earmark" aria-hidden="true"></i><span>{t('Files')}</span><b>{floor}<CountUp value={content.files} /></b></div>
    </div>
    {#if content.truncated}<small class="cc__note">{t('Very large folder: the figures are a minimum (the first 300,000 entries).')}</small>{/if}
    <!-- Another folder or a new measure: the bars fill again -->
    {#key content}
    <div class="cc__charts">
      {#if top.length}
        <div class="cc__chart">
          <h3>{t('Where the weight is')}</h3>
          {#each top as row, rank (row.name)}
            <div class="cc__bar" title={`${row.name} · ${size(row.bytes)} · ${t('{count} file(s)', { count: row.files })}`}>
              <span class="cc__label">{row.name}</span>
              <span class="cc__track"><i class="b2s-grow" style="width:{Math.max(2, (row.bytes / maxTop) * 100)}%;--i:{rank}"></i></span>
              <span class="cc__value">{size(row.bytes)}</span>
            </div>
          {/each}
        </div>
      {/if}
      {#if types.length}
        <div class="cc__chart">
          <h3>{t('File types')}</h3>
          {#each types as row, rank (row.ext)}
            <div class="cc__bar">
              <span class="cc__label mono">{row.ext === '—' ? t('no extension') : `.${row.ext}`}</span>
              <span class="cc__track"><i class="b2s-grow" style="width:{Math.max(2, (row.files / maxType) * 100)}%;--i:{rank}"></i></span>
              <span class="cc__value">{count(row.files)}</span>
            </div>
          {/each}
        </div>
      {/if}
    </div>
    {/key}
    <!-- Age of the data, duplicates, clutter and growth: the module « 5S et hygiène des données » -->
    {#if $fivesEnabled && ages.length}
      <div class="cc__age">
        <div class="cc__age-head">
          <h3>{t('Age of the data')}</h3>
          {#if content.last_modified}<small>{t('last change {when}', { when: timeAgo(content.last_modified) })}</small>{/if}
        </div>
        <div class="cc__stack" role="img" aria-label={ages.map((age) => `${age.label} : ${pct(age.bytes)} %`).join(', ')}>
          {#each ages as age, rank (age.key)}{#if age.bytes > 0}<i class={`b2s-grow is-${age.key}`} style={`flex:${age.bytes};--i:${rank}`}></i>{/if}{/each}
        </div>
        <ul class="cc__legend">
          {#each ages as age (age.key)}<li><span class={`cc__key is-${age.key}`}></span>{age.label} <b>{pct(age.bytes)} %</b> <small>{size(age.bytes)}</small></li>{/each}
        </ul>
        {#if content.cold_top?.length}
          <details class="cc__more">
            <summary>{t('Biggest files untouched for a year')}</summary>
            <ul>{#each content.cold_top as file (file.path)}<li><code title={file.path} data-copy={file.path}>{file.path}</code><span>{size(file.bytes)} · {timeAgo(file.modified)}</span></li>{/each}</ul>
          </details>
        {/if}
      </div>
    {/if}
    {#if $fivesEnabled && (dups?.groups || shared?.files)}
      <div class="cc__dups">
        <div class="cc__age-head">
          <h3>{t('Duplicates')}</h3>
          <small>{t('same size and same fingerprint')}{dups?.truncated ? ` · ${t('partial: hashing budget reached')}` : ''}</small>
        </div>
        {#if dups?.groups}
          <p><b>{size(dups.wasted_bytes)}</b> {t('to free in the folder')} · {t('{count} group(s) of copies, {files} file(s)', { count: dups.groups, files: dups.files })}</p>
          <ul class="cc__dup-list">
            {#each dups.top.slice(0, 5) as group (group.paths.join('|'))}
              <li><span class="cc__dup-n">×{group.files}</span><span class="cc__dup-paths">{#each group.paths.slice(0, 3) as path (path)}<code title={path} data-copy={path}>{path}</code>{/each}</span><span class="cc__dup-size">{size(group.size)}</span></li>
            {/each}
          </ul>
        {/if}
        {#if shared?.files}
          <p><b>{size(shared.bytes)}</b> {t('also present in {count} other folder(s)', { count: shared.with.length })}</p>
          <ul class="cc__dup-list">
            {#each shared.examples as file (file.path)}
              <li><span class="cc__dup-n"><i class="bi bi-files" aria-hidden="true"></i></span><span class="cc__dup-paths"><code title={file.path} data-copy={file.path}>{file.path}</code><small>{t('also in')} {file.also_in.join(', ')}</small></span><span class="cc__dup-size">{size(file.size)}</span></li>
            {/each}
          </ul>
        {/if}
      </div>
    {/if}
    {#if $fivesEnabled && content.junk?.files}
      <div class="cc__junk">
        <i class="bi bi-trash3" aria-hidden="true"></i>
        <span><b>{t('{count} clutter file(s)', { count: content.junk.files })}</b> · {size(content.junk.bytes)}
          <small>{t('Thumbnail caches, Office lock files, temporary files, backups and copies')} — {content.junk.examples.slice(0, 3).join(', ')}</small></span>
      </div>
    {/if}
    {#if $fivesEnabled}<StorageRootGrowth {rootId} refreshKey={content.scanned_at} />{/if}
  {:else}
    <p class="cc__empty">{t('The size, the age of the data and the duplicates appear after the first measure of the folder.')}</p>
  {/if}
</section>

<style>
  .cc { display: flex; flex-direction: column; gap: 12px; padding: 16px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  .cc header { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
  .cc h2 { margin: 0; font-size: var(--b2s-fs-md); font-weight: 600; }
  .cc header small, .cc__note, .cc__empty { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .cc__empty { margin: 0; }
  .cc__tiles { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
  .cc__tile { display: grid; grid-template-columns: auto 1fr; grid-template-rows: auto auto; column-gap: 10px; align-items: center; padding: 12px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-md); }
  .cc__tile i { grid-row: 1 / 3; display: grid; place-items: center; width: 34px; height: 34px; border-radius: var(--b2s-radius-md); background: var(--b2s-color-info-soft); color: var(--b2s-color-info-strong); font-size: 16px; }
  .cc__tile span { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .cc__tile b { font-size: 20px; font-weight: 700; font-variant-numeric: tabular-nums; }
  .cc__charts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
  .cc__chart { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
  .cc__chart h3 { margin: 0 0 2px; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; }
  .cc__bar { display: grid; grid-template-columns: minmax(70px, 34%) minmax(0, 1fr) 64px; gap: 8px; align-items: center; font-size: var(--b2s-fs-xs); }
  .cc__label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .cc__track { height: 8px; border-radius: var(--b2s-radius-pill); background: var(--b2s-color-neutral-soft); overflow: hidden; }
  .cc__track i { display: block; height: 100%; border-radius: inherit; background: var(--b2s-color-info-strong); }
  .cc__value { text-align: right; font-variant-numeric: tabular-nums; color: var(--b2s-color-text-muted); }
  .mono { font-family: var(--b2s-font-mono); }
  .cc__age { display: flex; flex-direction: column; gap: 8px; padding-top: 12px; border-top: 1px solid var(--b2s-color-border); }
  .cc__age-head { display: flex; align-items: baseline; justify-content: space-between; }
  .cc__age h3 { margin: 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; }
  .cc__age-head small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  /* One hue, three steps: light = recent, dark = frozen (sequential); a 2px gap between segments */
  .cc__stack { display: flex; gap: 2px; height: 12px; border-radius: var(--b2s-radius-pill); overflow: hidden; background: var(--b2s-color-neutral-soft); }
  .cc__stack i { display: block; height: 100%; }
  .is-fresh { background: #9ec5fe; }
  .is-cold { background: #3b82f6; }
  .is-frozen { background: #1e3a8a; }
  .cc__legend { display: flex; flex-wrap: wrap; gap: 4px 16px; margin: 0; padding: 0; list-style: none; font-size: var(--b2s-fs-xs); }
  .cc__legend li { display: flex; align-items: center; gap: 6px; }
  .cc__legend small { color: var(--b2s-color-text-muted); }
  .cc__key { width: 10px; height: 10px; border-radius: 3px; }
  .cc__more summary { cursor: pointer; color: var(--b2s-color-info-strong); font-size: var(--b2s-fs-xs); }
  .cc__more ul { display: flex; flex-direction: column; gap: 4px; margin: 6px 0 0; padding: 0; list-style: none; font-size: var(--b2s-fs-xs); }
  .cc__more li { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 10px; }
  .cc__more code { color: var(--b2s-color-text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-family: var(--b2s-font-mono); }
  .cc__more span { color: var(--b2s-color-text-muted); font-variant-numeric: tabular-nums; }
  .cc__progress { height: 6px; border-radius: var(--b2s-radius-pill); background: var(--b2s-color-neutral-soft); overflow: hidden; }
  .cc__progress span { display: block; height: 100%; background: var(--b2s-color-info-strong); transition: width var(--b2s-motion-slow) var(--b2s-ease-out); }
  .cc__fail { display: flex; gap: 8px; margin: 0; color: var(--b2s-color-danger-strong, #b42318); font-size: var(--b2s-fs-sm); }
  .cc__note code { font-family: var(--b2s-font-mono); }
  .cc__dups { display: flex; flex-direction: column; gap: 8px; padding-top: 12px; border-top: 1px solid var(--b2s-color-border); }
  .cc__dups p { margin: 0; font-size: var(--b2s-fs-sm); }
  .cc__dups h3 { margin: 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; }
  .cc__dups .cc__age-head small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .cc__dup-list { display: flex; flex-direction: column; gap: 6px; margin: 0; padding: 0; list-style: none; font-size: var(--b2s-fs-xs); }
  .cc__dup-list li { display: grid; grid-template-columns: 36px minmax(0, 1fr) auto; gap: 10px; align-items: start; }
  .cc__dup-n { display: grid; place-items: center; padding: 1px 0; border-radius: var(--b2s-radius-pill); background: var(--b2s-color-info-soft); color: var(--b2s-color-info-strong); font-weight: 700; }
  .cc__dup-paths { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
  .cc__dup-paths code { color: var(--b2s-color-text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-family: var(--b2s-font-mono); }
  .cc__dup-paths small { color: var(--b2s-color-text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .cc__dup-size { color: var(--b2s-color-text-muted); font-variant-numeric: tabular-nums; }
  .cc__junk { display: flex; gap: 10px; align-items: flex-start; padding: 10px 12px; border-radius: var(--b2s-radius-md); background: var(--b2s-color-warning-soft, #fff4e5); font-size: var(--b2s-fs-sm); }
  .cc__junk i { color: var(--b2s-color-warning-strong, #9a5b00); margin-top: 2px; }
  .cc__junk small { display: block; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
</style>
