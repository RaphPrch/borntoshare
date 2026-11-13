<script lang="ts">

  import { fivesEnabled } from '$lib/utils/features';
  import { onDestroy, onMount } from 'svelte';
  import { page } from '$app/stores';
  import { apiGetData, apiPostData, apiPutData } from '$lib/api/client';
  import FivesTabs from '$lib/components/fives/FivesTabs.svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import RelativeTime from '$lib/components/ui/RelativeTime.svelte';
  import { reportUiError } from '$lib/errors';
  import { t } from '$lib/i18n';
  import { toast } from '$lib/stores/toast';
  import { formatBytes } from '$lib/utils/format';

  /**
   * 5S › Scanner: the queue of the scanner of the module (one or more instances, no agent on the file servers), what
   * it is walking now, its last scans (full or incremental through the NTFS change journal), and its settings.
   */
  type Run = { id: number; storage_root_id: number; folder_name: string | null; host: string; status: string; reason: string; mode: string | null;
    requested_by: string | null; requested_at: string | null; started_at: string | null; finished_at: string | null; scanner_id: string | null;
    progress: { chunks_total: number; chunks_done: number; chunks_kept: number; files: number; current: string | null; mode: string } | null;
    summary: { mode: string; chunks_walked: number; chunks_kept: number; files: number; bytes: number; elapsed_ms: number } | null; error: string | null };
  type Settings = { schedule_enabled: boolean; window_start: string; window_end: string; per_server: number; interval_days: number; full_every_days: number; hash_files_max: number };
  type Data = { runs: Run[]; counts: Record<string, number>; scanners: Array<{ id: string; last_seen: string }>; settings: Settings; in_window: boolean };

  let data = $state<Data | null>(null);
  let error = $state('');
  let form = $state<Settings | null>(null);
  let busy = $state(false);
  let filter = $state<'active' | 'all'>('active');
  let timer: ReturnType<typeof setInterval> | null = null;

  async function load() {
    try {
      data = await apiGetData<Data>(fetch, '/modules/fives/scans');
      if (!form) form = { ...data.settings };
      error = '';
    } catch (failure) {
      error = failure instanceof Error ? failure.message : t('Unable to load the scanner.');
    }
  }
  onMount(() => {
    // Not active (no license, switched off, or not installed): the explanation, no call to the module
    if (!$fivesEnabled) return;
    load();
    timer = setInterval(load, 5000);
  });
  onDestroy(() => timer && clearInterval(timer));

  // Long queues (a first planning of hundreds of folders) are shown 20 at a time
  const PAGE = 20;
  let showAll = $state(false);
  const STATUS = (): Record<string, string> => ({ queued: t('Waiting'), running: t('Walking'), done: t('Done'), failed: t('Failed'),
    delegated: t('Through SMB'), cancelled: t('Cancelled') });
  const REASON = (): Record<string, string> => ({ manual: t('asked'), policy: t('policy'), schedule: t('schedule') });
  const seconds = (ms: number) => (ms < 1000 ? `${ms} ms` : ms < 60000 ? `${(ms / 1000).toLocaleString('fr-FR', { maximumFractionDigits: 1 })} s` : `${Math.round(ms / 60000)} min`);

  async function save() {
    if (!form || busy) return;
    busy = true;
    try {
      const saved = await apiPutData<Settings>(fetch, '/modules/fives/settings', form);
      form = { ...saved };
      toast.success(t('Scanner settings saved.'));
      await load();
    } catch (failure: unknown) {
      reportUiError(failure, 'Unable to save the settings.', 'fives.settings');
    } finally {
      busy = false;
    }
  }
  async function cancel(run: Run) {
    try {
      await apiPostData(fetch, `/modules/fives/scans/${run.id}/cancel`, {});
      await load();
    } catch (failure: unknown) {
      reportUiError(failure, 'Unable to cancel the scan.', 'fives.cancel');
    }
  }
  let isAdmin = $derived(($page.data as any)?.me?.is_admin === true);
  $effect.pre(() => {
    if (filter) showAll = false;
  });
  let runs = $derived((data?.runs ?? []).filter((run) => filter === 'all' || run.status === 'queued' || run.status === 'running'));
  let shown = $derived(showAll ? runs : runs.slice(0, PAGE));
</script>

<section class="b2s-page b2s-page--admin sc5">
  <FivesTabs />
  <header class="sc5__head">
    <div>
      <h1>{t('Scanner')}</h1>
      <p>{t('Walks the folders on their file servers, without agent: one server at a time, inside the window, only what changed.')}</p>
    </div>
  </header>

  {#if !$fivesEnabled}
    <InlineAlert tone="info">{t('The 5S module is not active')} : {t('It is opened by a license key and switched on by an administrator in Advanced settings › Features; its databases are installed by the installation wizard.')}</InlineAlert>
  {:else if error}
    <InlineAlert tone="error">{error}</InlineAlert>
  {:else if !data}
    <LoadingState block skeleton="rows" rows={5} />
  {:else}
    <div class="sc5__kpis">
      <div class:is-on={data.in_window}><span>{t('Window')}</span><b>{data.settings.window_start} → {data.settings.window_end}</b>
        <small>{data.in_window ? t('open now: the scheduled scans run') : t('closed: only the scans asked by a person run')}</small></div>
      <div><span>{t('Walking')}</span><b>{data.counts.running ?? 0}</b><small>{t('at most {count} per server', { count: data.settings.per_server })}</small></div>
      <div><span>{t('Waiting')}</span><b>{data.counts.queued ?? 0}</b><small>{t('scans in the queue')}</small></div>
      <div><span>{t('Scanners')}</span><b>{data.scanners.length}</b>
        <small>{data.scanners.length ? data.scanners.map((scanner) => scanner.id).join(', ') : t('none seen in the last 24 h')}</small></div>
    </div>

    <section class="sc5__card" aria-label={t('Queue')}>
      <header>
        <h2>{t('Scans')}</h2>
        <span class="sc5__seg">
          <button type="button" class:is-on={filter === 'active'} onclick={() => (filter = 'active')}>{t('In progress')}</button>
          <button type="button" class:is-on={filter === 'all'} onclick={() => (filter = 'all')}>{t('Last 7 days')}</button>
        </span>
      </header>
      {#each shown as run (run.id)}
        <div class="sc5__run" data-status={run.status}>
          <span class="sc5__status">{STATUS()[run.status] ?? run.status}</span>
          <span class="sc5__what">
            <a href={`/storage-roots?selected=${run.storage_root_id}`}><b>{run.folder_name ?? `#${run.storage_root_id}`}</b></a>
            <small>{run.host} · {REASON()[run.reason] ?? run.reason}{run.requested_by ? ` · ${run.requested_by}` : ''} · <RelativeTime value={run.requested_at} />{run.scanner_id ? ` · ${run.scanner_id}` : ''}</small>
            {#if run.status === 'running' && run.progress}
              <span class="sc5__bar"><i style={`width:${run.progress.chunks_total ? Math.round((run.progress.chunks_done / run.progress.chunks_total) * 100) : 0}%`}></i></span>
              <small>{run.progress.mode === 'incremental' ? t('incremental') : t('full walk')} · {run.progress.chunks_done}/{run.progress.chunks_total} · {run.progress.files.toLocaleString('fr-FR')} {t('file(s)')}{run.progress.current ? ` · ${run.progress.current}` : ''}</small>
            {:else if run.summary}
              <small>{run.summary.mode === 'incremental' ? t('incremental: {walked} sub-folder(s) walked, {kept} kept', { walked: run.summary.chunks_walked, kept: run.summary.chunks_kept }) : t('full walk')}
                · {run.summary.files.toLocaleString('fr-FR')} {t('file(s)')} · {formatBytes(run.summary.bytes)} · {seconds(run.summary.elapsed_ms)}</small>
            {:else if run.error}
              <small class="sc5__err">{run.error}</small>
            {/if}
          </span>
          {#if isAdmin && run.status === 'queued'}<button type="button" class="b2s-link-btn" onclick={() => cancel(run)}>{t('Cancel')}</button>{/if}
        </div>
      {:else}
        <p class="sc5__empty">{filter === 'active' ? t('Nothing in progress: the scanner waits.') : t('No scan in the last 7 days.')}</p>
      {/each}
      {#if runs.length > shown.length}
        <button type="button" class="b2s-link-btn sc5__more" onclick={() => (showAll = true)}>{t('Show the {count} others', { count: runs.length - shown.length })}</button>
      {/if}
    </section>

    {#if isAdmin && form}
      <section class="sc5__card" aria-label={t('Settings')}>
        <header><h2>{t('Settings')}</h2></header>
        <form class="sc5__form" onsubmit={(event) => { event.preventDefault(); save(); }}>
          <label class="sc5__check"><input type="checkbox" bind:checked={form.schedule_enabled} /> {t('Scan every folder on schedule')}</label>
          <label>{t('Window from')}<input class="b2s-input" type="time" bind:value={form.window_start} /></label>
          <label>{t('to')}<input class="b2s-input" type="time" bind:value={form.window_end} /></label>
          <label>{t('Every (days)')}<input class="b2s-input" type="number" min="1" max="90" bind:value={form.interval_days} /></label>
          <label>{t('Scans at a time per server')}<input class="b2s-input" type="number" min="1" max="8" bind:value={form.per_server} /></label>
          <label>{t('Full walk every (days)')}<input class="b2s-input" type="number" min="1" max="365" bind:value={form.full_every_days} /></label>
          <label>{t('Fingerprints per piece (duplicates)')}<input class="b2s-input" type="number" min="0" max="500000" step="1000" bind:value={form.hash_files_max} /></label>
          <p class="sc5__hint">{t('Between two full walks, only the sub-folders where the NTFS change journal shows a change are walked again. A server that cannot be walked on (DFS namespace, no WinRM) is measured through SMB by the worker of the core.')}</p>
          <div class="sc5__btns"><button type="submit" class="b2s-btn b2s-btn-primary b2s-btn-sm" disabled={busy}>{t('Save')}</button></div>
        </form>
      </section>
    {/if}
  {/if}
</section>

<style>
  .sc5 { display: flex; flex-direction: column; gap: 18px; padding: var(--b2s-page-padding, 24px 28px); }
  .sc5__head h1 { margin: 0; font-size: var(--b2s-fs-page-title, 24px); font-weight: 650; }
  .sc5__head p { margin: 4px 0 0; color: var(--b2s-color-text-muted); }
  .sc5__kpis { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
  .sc5__kpis > div { display: flex; flex-direction: column; gap: 2px; padding: 14px 16px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  .sc5__kpis > div.is-on { border-color: var(--b2s-color-success-border, #cfe9d9); background: var(--b2s-color-success-soft, #f3fbf6); }
  .sc5__kpis span { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .sc5__kpis b { font-size: 22px; font-weight: 650; font-variant-numeric: tabular-nums; }
  .sc5__kpis small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .sc5__card { display: flex; flex-direction: column; gap: 4px; padding: 16px 18px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  .sc5__card > header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
  .sc5__card h2 { margin: 0; font-size: var(--b2s-fs-md); font-weight: 600; }
  .sc5__seg { display: inline-flex; gap: 2px; padding: 3px; border-radius: 10px; background: var(--b2s-color-neutral-soft); }
  .sc5__seg button { padding: 5px 12px; border: 0; border-radius: 8px; background: transparent; color: var(--b2s-color-text-muted); font: inherit; font-size: var(--b2s-fs-xs); font-weight: 600; cursor: pointer; }
  .sc5__seg button.is-on { background: var(--b2s-color-surface); color: var(--b2s-color-text); box-shadow: 0 1px 3px rgba(14, 18, 24, 0.12); }
  .sc5__more { margin-top: 8px; }
  .sc5__run { display: grid; grid-template-columns: 110px minmax(0, 1fr) auto; gap: 12px; align-items: start; padding: 10px 0; border-top: 1px solid var(--b2s-color-border); }
  .sc5__status { justify-self: start; padding: 2px 10px; border-radius: var(--b2s-radius-pill); background: var(--b2s-color-neutral-soft); font-size: var(--b2s-fs-xs); font-weight: 600; }
  .sc5__run[data-status='running'] .sc5__status { background: var(--b2s-color-info-soft); color: var(--b2s-color-info-strong); }
  .sc5__run[data-status='done'] .sc5__status { background: var(--b2s-color-success-soft, #eaf7ee); color: var(--b2s-color-success-strong, #1a7f37); }
  .sc5__run[data-status='failed'] .sc5__status { background: var(--b2s-color-danger-soft, #fdecea); color: var(--b2s-color-danger-strong, #b42318); }
  .sc5__what { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
  .sc5__what a { color: inherit; text-decoration: none; }
  .sc5__what small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .sc5__err { color: var(--b2s-color-danger-strong, #b42318) !important; }
  .sc5__bar { height: 6px; border-radius: var(--b2s-radius-pill); background: var(--b2s-color-neutral-soft); overflow: hidden; max-width: 420px; }
  .sc5__bar i { display: block; height: 100%; background: var(--b2s-color-info-strong); transition: width var(--b2s-motion-slow) var(--b2s-ease-out); }
  .sc5__empty { margin: 8px 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .sc5__form { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
  .sc5__form label { display: flex; flex-direction: column; gap: 5px; font-size: var(--b2s-fs-sm); font-weight: 500; }
  .sc5__form label.sc5__check { grid-column: 1 / -1; flex-direction: row; align-items: center; gap: 8px; }
  .sc5__hint { grid-column: 1 / -1; margin: 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .sc5__btns { grid-column: 1 / -1; display: flex; justify-content: flex-end; }
</style>
