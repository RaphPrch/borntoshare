<script lang="ts">
  import MeasureCompleteness, { type Completeness, COMPLETENESS_LABEL } from '$lib/components/storage-roots/MeasureCompleteness.svelte';
  import QuarantineList, { type Move } from '../QuarantineList.svelte';
  import { onDestroy, onMount, untrack } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { apiGetData, apiGetList, apiPostData, apiPutData } from '$lib/api/client';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import RelativeTime from '$lib/components/ui/RelativeTime.svelte';
  import ContextMenu, { menuPositionFor, type ContextMenuItem } from '$lib/components/ui/ContextMenu.svelte';
  import { reportUiError } from '$lib/errors';
  import { t } from '$lib/i18n';
  import { toast } from '$lib/stores/toast';
  import { formatBytes, formatDateTime } from '$lib/utils/format';
  import { readParam, writeParams } from '$lib/utils/url-state';

  /**
   * Inventory (v2): the scanner of the 5S module (no agent on the file servers) in a dark band — its schedule, what
   * it walks, its queue — then three tabs: the scans (queue and last 7 days), the inventory of every folder
   * (last measure, files, volume, state) and the settings of the scanner.
   */
  type Run = { id: number; storage_root_id: number; folder_name: string | null; host: string; status: string; reason: string; mode: string | null;
    requested_by: string | null; requested_at: string | null; started_at: string | null; finished_at: string | null; scanner_id: string | null;
    progress: { chunks_total: number; chunks_done: number; chunks_kept: number; files: number; current: string | null; mode: string } | null;
    summary: { mode: string; chunks_walked: number; chunks_kept: number; files: number; bytes: number; elapsed_ms: number; completeness?: Completeness } | null; error: string | null };
  type Settings = { schedule_enabled: boolean; frequency: 'days' | 'hours'; window_start: string; window_end: string; per_server: number; interval_days: number;
    interval_hours: number; full_every_days: number; hash_files_max: number; quarantine_purge_days: number; file_owners: boolean };
  type Data = { runs: Run[]; counts: Record<string, number>; scanners: Array<{ id: string; last_seen: string }>; settings: Settings; in_window: boolean;
    next_window_at: string | null };
  type Root = Record<string, any>;

  let data = $state<Data | null>(null);
  let roots = $state<Root[]>([]);
  let error = $state('');
  let form = $state<Settings | null>(null);
  let busy = $state(false);
  // The tab and the folder may come from the address (« See the quarantine » of a folder)
  const asked = $page.url.searchParams.get('tab');
  let tab = $state<'queue' | 'folders' | 'quarantine' | 'settings'>(asked === 'folders' || asked === 'quarantine' || asked === 'settings' ? asked : 'queue');
  let quarantineRoot = $state<number | null>(Number($page.url.searchParams.get('root')) || null);
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
  // The columns this page reads only (the whole folder list weighed megabytes)
  const ROOT_FIELDS = 'storage_root_id,storage_root_name,root_path,storage_endpoint_name,zone_name,measure_status,content_size_bytes,content_files,content_updated_at';
  const loadRoots = async () => (roots = await apiGetList<Root>(fetch, '/storage-roots/context', { fields: ROOT_FIELDS }).catch(() => roots));
  // ---- quarantine and archives of every folder ----
  type QuarantineData = { moves: Move[]; counts: Record<string, number>; quarantine_bytes: number; purge_days: number };
  let quarantine = $state<QuarantineData | null>(null);
  let quarantineStatus = $state<'all' | 'moved' | 'pending' | 'failed' | 'restored'>('all');
  let quarantineKind = $state<'all' | 'duplicate' | 'archive'>('all');
  async function loadQuarantine() {
    const params: Record<string, string> = {};
    if (quarantineRoot) params.root_id = String(quarantineRoot);
    if (quarantineKind !== 'all') params.kind = quarantineKind;
    quarantine = await apiGetData<QuarantineData>(fetch, '/modules/fives/quarantine', params).catch(() => quarantine);
  }
  $effect.pre(() => {
    void [quarantineRoot, quarantineKind];
    if (tab === 'quarantine') untrack(() => void loadQuarantine());
  });
  let quarantineRows = $derived((quarantine?.moves ?? []).filter((move) => quarantineStatus === 'all'
    || (quarantineStatus === 'pending' ? move.status.endsWith('pending') : quarantineStatus === 'failed' ? move.status.endsWith('failed') : move.status === quarantineStatus)));
  async function restoreMoves(moves: Move[]) {
    let done = 0;
    for (const move of moves) {
      try {
        await apiPostData(fetch, `/modules/fives/storage-roots/${move.storage_root_id}/quarantine/${move.id}/restore`, {});
        done += 1;
      } catch (failure) {
        reportUiError(failure, t('Unable to restore the copy.'), 'fives.quarantine.restore');
      }
    }
    if (done) toast.success(t('{count} copy(ies) or folder(s) go back to their place.', { count: done }));
    await loadQuarantine();
  }

  // ---- complete, partial or sampled: the last measure of each folder ----
  let states = $state<Record<string, { status: Completeness['status']; reasons: string[] }>>({});
  const loadStates = async () => (states = (await apiGetData<typeof states>(fetch, '/modules/fives/measures/states').catch(() => null)) ?? states);

  onMount(() => {
    void load();
    void loadRoots();
    void loadStates();
    timer = setInterval(() => { void load(); if (tab === 'quarantine' && quarantine?.moves.some((move) => move.status.endsWith('pending'))) void loadQuarantine(); }, 5000);
  });
  onDestroy(() => timer && clearInterval(timer));

  // Long queues (a first planning of hundreds of folders) are shown 20 at a time
  const PAGE = 20;
  let showAll = $state(false);
  const STATUS = (): Record<string, string> => ({ queued: t('Waiting'), running: t('Walking'), done: t('Done'), failed: t('Failed'),
    delegated: t('Through SMB'), cancelled: t('Cancelled') });
  const STATUS_TONE: Record<string, string> = { queued: 'mut', running: 'info', done: 'ok', failed: 'bad', delegated: 'warn', cancelled: 'mut' };
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
  async function measure(ids: number[]) {
    if (!ids.length) return;
    try {
      const result = await apiPostData<{ queued: number[] }>(fetch, '/storage-roots/measure', { root_ids: ids });
      toast.success(t('Measure started on {count} folder(s).', { count: result?.queued?.length ?? ids.length }));
      await Promise.all([load(), loadRoots()]);
    } catch (failure: unknown) {
      reportUiError(failure, t('Unable to start the measure.'), 'fives.measure');
    }
  }
  /** The schedule in words: « Every day from 20:00 to 06:00 », « Every 6 hours » */
  function scheduleText(settings: Settings): string {
    if (!settings.schedule_enabled) return t('Off: only the scans asked by a person or a policy');
    if (settings.frequency === 'hours') return t('Every {count} hour(s), at any time', { count: settings.interval_hours });
    return settings.interval_days === 1
      ? t('Every day, from {start} to {end}', { start: settings.window_start, end: settings.window_end })
      : t('Every {count} days, from {start} to {end}', { count: settings.interval_days, start: settings.window_start, end: settings.window_end });
  }
  function nextText(value: Data): string {
    if (!value.next_window_at) return t('No scheduled scan');
    if (value.in_window) return value.settings.frequency === 'hours' ? t('runs continuously: each folder when its time comes') : t('running now, until {end}', { end: value.settings.window_end });
    return t('next run: {date}', { date: formatDateTime(value.next_window_at) });
  }
  let isAdmin = $derived(($page.data as any)?.me?.is_admin === true);
  $effect.pre(() => {
    if (filter) showAll = false;
  });
  let runs = $derived((data?.runs ?? []).filter((run) => filter === 'all' || run.status === 'queued' || run.status === 'running'));
  let shown = $derived(showAll ? runs : runs.slice(0, PAGE));

  // ---- inventory of the folders ----
  type FolderFilter = 'all' | 'active' | 'failed' | 'never' | 'done' | 'partial';
  let folderFilter = $state<FolderFilter>(readParam<FolderFilter>('filter', 'all', ['all', 'active', 'failed', 'never', 'done', 'partial']));
  // The tab, the filter of the folders and the folder of the quarantine stay in the address
  $effect(() => writeParams({ tab: tab === 'queue' ? null : tab, filter: folderFilter === 'all' ? null : folderFilter, root: tab === 'quarantine' ? quarantineRoot : null }));
  let folderQuery = $state('');
  let folderShown = $state(50);
  const num = (value: unknown) => (Number.isFinite(Number(value)) ? Number(value) : 0);
  const stateOf = (row: Root): { key: FolderFilter; label: string; tone: string } => {
    const status = String(row.measure_status ?? '');
    if (status === 'running' || status === 'queued') return { key: 'active', label: status === 'running' ? t('Walking') : t('Waiting'), tone: 'info' };
    if (status === 'failed') return { key: 'failed', label: t('Failed'), tone: 'bad' };
    if (row.content_size_bytes == null && status !== 'done') return { key: 'never', label: t('Never measured'), tone: 'warn' };
    return { key: 'done', label: t('Measured'), tone: 'ok' };
  };
  const FILTERS: Array<{ key: FolderFilter; label: () => string }> = [
    { key: 'all', label: () => t('All') }, { key: 'active', label: () => t('In progress') }, { key: 'failed', label: () => t('Failed') },
    { key: 'never', label: () => t('Never measured') }, { key: 'done', label: () => t('Measured') },
    { key: 'partial', label: () => t('Partial or sampled') }
  ];
  const measureState = (row: Root) => states[String(row.storage_root_id)];
  const inFilter = (row: Root, key: FolderFilter) => key === 'all' || (key === 'partial'
    ? ['partial', 'sampled'].includes(measureState(row)?.status ?? '') : stateOf(row).key === key);
  let folderNeedle = $derived(folderQuery.trim().toLowerCase());
  let folderRows = $derived(roots
    .filter((row) => inFilter(row, folderFilter) &&
      (!folderNeedle || `${row.storage_root_name ?? ''} ${row.root_path ?? ''} ${row.storage_endpoint_name ?? ''}`.toLowerCase().includes(folderNeedle)))
    .slice()
    .sort((a, b) => String(b.content_updated_at ?? '').localeCompare(String(a.content_updated_at ?? ''))));
  let neverIds = $derived(roots.filter((row) => stateOf(row).key === 'never').map((row) => Number(row.storage_root_id)));

  // ---- right click on a scan or a folder ----
  type Target = { id: number; name: string; run?: Run };
  let menu = $state<{ target: Target; at: { x: number; y: number } } | null>(null);
  let menuItems = $derived<ContextMenuItem[]>([
    { key: 'open', label: t('Open the folder sheet'), icon: 'bi-folder2-open' },
    { key: 'explore', label: t('Explore the content'), icon: 'bi-columns-gap' },
    ...(isAdmin ? [{ key: 'measure', label: t('Measure now'), icon: 'bi-rulers', separated: true }] : []),
    ...(isAdmin && menu?.target.run?.status === 'queued' ? [{ key: 'cancel', label: t('Cancel the scan'), icon: 'bi-x-circle', danger: true }] : [])
  ]);
  function onPick(key: string) {
    const target = menu?.target;
    if (!target) return;
    if (key === 'open') void goto(`/storage-roots?selected=${target.id}`);
    if (key === 'explore') void goto(`/five-s/explore/${target.id}`);
    if (key === 'measure') void measure([target.id]);
    if (key === 'cancel' && target.run) void cancel(target.run);
  }
  const openMenu = (target: Target) => (event: MouseEvent) => {
    event.preventDefault();
    menu = { target, at: menuPositionFor(event) };
  };
</script>

<section class="v2 sc5">
  <div class="v2-head">
    <div>
      <h1>Inventory</h1>
      <p>{t('The measures of the folders: full or incremental (NTFS change journal), without agent, one server at a time, inside the window.')}</p>
    </div>
    {#if isAdmin && neverIds.length}
      <div class="v2-head__act"><button type="button" class="b2s-btn b2s-btn-primary" onclick={() => measure(neverIds)}>
        <i class="bi bi-rulers" aria-hidden="true"></i>{t('Measure the {count} folder(s) never measured', { count: neverIds.length })}</button></div>
    {/if}
  </div>

  {#if error}
    <InlineAlert tone="error">{error}</InlineAlert>
  {:else if !data}
    <LoadingState block skeleton="rows" rows={5} />
  {:else}
    <div class="sc5__band">
      <div class="sc5__sched" class:is-on={data.in_window && data.settings.schedule_enabled}>
        <small>{t('Schedule')}</small><b>{scheduleText(data.settings)}</b><span>{nextText(data)}</span>
      </div>
      <div class="v2-stats sc5__stats">
        <div class="v2-stat"><i class="bi bi-activity" aria-hidden="true"></i><small>{t('Walking')}</small><b>{data.counts.running ?? 0}</b><span>{t('at most {count} per server', { count: data.settings.per_server })}</span></div>
        <div class="v2-stat"><i class="bi bi-hourglass-split" aria-hidden="true"></i><small>{t('Waiting')}</small><b>{data.counts.queued ?? 0}</b><span>{t('scans in the queue')}</span></div>
        <div class="v2-stat"><i class="bi bi-cpu" aria-hidden="true"></i><small>{t('Scanners')}</small><b>{data.scanners.length}</b><span>{data.scanners.length ? data.scanners.map((scanner) => scanner.id).join(', ') : t('none seen in the last 24 h')}</span></div>
        <div class="v2-stat"><i class="bi bi-question-circle is-warn" aria-hidden="true"></i><small>{t('Never measured')}</small><b>{neverIds.length}</b><span>{t('{count} folder(s) in all', { count: roots.length })}</span></div>
      </div>
    </div>

    <div class="v2-tabs" role="tablist" aria-label={t('Inventory')}>
      <button type="button" role="tab" class:is-on={tab === 'queue'} aria-selected={tab === 'queue'} onclick={() => (tab = 'queue')}>{t('Scans')}{#if (data.counts.running ?? 0) + (data.counts.queued ?? 0)}<b>{(data.counts.running ?? 0) + (data.counts.queued ?? 0)}</b>{/if}</button>
      <button type="button" role="tab" class:is-on={tab === 'folders'} aria-selected={tab === 'folders'} onclick={() => (tab = 'folders')}>{t('Folders')}<b>{roots.length}</b></button>
      <button type="button" role="tab" class:is-on={tab === 'quarantine'} aria-selected={tab === 'quarantine'} onclick={() => (tab = 'quarantine')}>{t('Quarantine')}{#if quarantine?.counts.moved}<b>{quarantine.counts.moved}</b>{/if}</button>
      {#if isAdmin && form}<button type="button" role="tab" class:is-on={tab === 'settings'} aria-selected={tab === 'settings'} onclick={() => (tab = 'settings')}>{t('Settings')}</button>{/if}
    </div>

    {#if tab === 'queue'}
      <div class="v2-sec">
        <div class="v2-sh">
          <div class="v2-seg" role="group" aria-label={t('Show')}>
            <button type="button" class:is-on={filter === 'active'} onclick={() => (filter = 'active')}>{t('In progress')}</button>
            <button type="button" class:is-on={filter === 'all'} onclick={() => (filter = 'all')}>{t('Last 7 days')}</button>
          </div>
          <div class="v2-sh__r"><span class="v2-hint">{t('Right click: open, explore, measure again, cancel')}</span></div>
        </div>
        <div class="v2-list">
          {#each shown as run (run.id)}
            <div class="v2-row sc5__run" role="row" tabindex="-1" oncontextmenu={openMenu({ id: run.storage_root_id, name: run.folder_name ?? `#${run.storage_root_id}`, run })}>
              <span><span class={`v2-tag is-${STATUS_TONE[run.status] ?? 'mut'}`}>{STATUS()[run.status] ?? run.status}</span></span>
              <span class="v2-nm">
                <a href={`/storage-roots?selected=${run.storage_root_id}`}>{run.folder_name ?? `#${run.storage_root_id}`}</a>
                <span class="v2-sub">{run.host} · {REASON()[run.reason] ?? run.reason}{run.requested_by ? ` · ${run.requested_by}` : ''} · <RelativeTime value={run.requested_at} />{run.scanner_id ? ` · ${run.scanner_id}` : ''}</span>
                {#if run.status === 'running' && run.progress}
                  <span class="v2-bar is-accent sc5__bar"><i style={`width:${run.progress.chunks_total ? Math.round((run.progress.chunks_done / run.progress.chunks_total) * 100) : 0}%`}></i></span>
                  <span class="v2-sub">{run.progress.mode === 'incremental' ? t('incremental') : t('full walk')} · {run.progress.chunks_done}/{run.progress.chunks_total} · {run.progress.files.toLocaleString('fr-FR')} {t('file(s)')}{run.progress.current ? ` · ${run.progress.current}` : ''}</span>
                {:else if run.summary}
                  {#if run.summary.completeness}<span><MeasureCompleteness value={run.summary.completeness} compact /></span>{/if}
                  <span class="v2-sub">{run.summary.mode === 'incremental' ? t('incremental: {walked} sub-folder(s) walked, {kept} kept', { walked: run.summary.chunks_walked, kept: run.summary.chunks_kept }) : t('full walk')}
                    · {run.summary.files.toLocaleString('fr-FR')} {t('file(s)')} · {formatBytes(run.summary.bytes)} · {seconds(run.summary.elapsed_ms)}</span>
                {:else if run.error}
                  <span class="v2-sub sc5__err">{run.error}</span>
                {/if}
              </span>
              <span class="sc5__end">
                {#if isAdmin && run.status === 'queued'}<button type="button" class="b2s-link-btn" onclick={() => cancel(run)}>{t('Cancel')}</button>{/if}
                <button type="button" class="v2-dots" aria-label={t('Actions on {name}', { name: run.folder_name ?? '' })} title={t('Actions on {name}', { name: run.folder_name ?? '' })}
                  onclick={openMenu({ id: run.storage_root_id, name: run.folder_name ?? `#${run.storage_root_id}`, run })}><i class="bi bi-three-dots" aria-hidden="true"></i></button>
              </span>
            </div>
          {:else}
            <p class="v2-empty">{filter === 'active' ? t('Nothing in progress: the scanner waits.') : t('No scan in the last 7 days.')}</p>
          {/each}
        </div>
        {#if runs.length > shown.length}
          <button type="button" class="b2s-link-btn sc5__more" onclick={() => (showAll = true)}>{t('Show the {count} others', { count: runs.length - shown.length })}</button>
        {/if}
      </div>
    {:else if tab === 'folders'}
      <div class="v2-sec">
        <div class="v2-sh">
          <div class="v2-seg" role="group" aria-label={t('Quick filters')}>
            {#each FILTERS as item (item.key)}
              <button type="button" class:is-on={folderFilter === item.key} onclick={() => { folderFilter = item.key; folderShown = 50; }}>
                {item.label()} <b>{roots.filter((row) => inFilter(row, item.key)).length}</b></button>
            {/each}
          </div>
          <div class="v2-sh__r"><label class="v2-search"><i class="bi bi-search" aria-hidden="true"></i><input type="search" bind:value={folderQuery} placeholder={t('Folder, path, server…')} aria-label={t('Search a folder')} /></label></div>
        </div>
        <div class="v2-list">
          <div class="v2-row is-head sc5__g"><span>{t('Folder')}</span><span>{t('Server')}</span><span>{t('Files')}</span><span>{t('Volume')}</span><span>{t('Measured')}</span><span>{t('State')}</span><span></span></div>
          {#each folderRows.slice(0, folderShown) as row (row.storage_root_id)}
            {@const state = stateOf(row)}
            {@const target = { id: Number(row.storage_root_id), name: String(row.storage_root_name ?? '') }}
            <div class="v2-row sc5__g" role="row" tabindex="-1" oncontextmenu={openMenu(target)}>
              <span class="v2-nm"><a href={`/storage-roots?selected=${row.storage_root_id}`}>{row.storage_root_name}</a><small>{row.root_path}</small></span>
              <span class="v2-nm"><span>{row.storage_endpoint_name ?? '—'}</span><span class="v2-sub">{row.zone_name ?? ''}</span></span>
              <span>{row.content_files != null ? num(row.content_files).toLocaleString('fr-FR') : '—'}</span>
              <span>{row.content_size_bytes != null ? formatBytes(num(row.content_size_bytes)) : '—'}</span>
              <span class="v2-sub">{#if row.content_updated_at}<RelativeTime value={row.content_updated_at} />{:else}—{/if}</span>
              <span class="sc5__states"><span class={`v2-tag is-${state.tone}`}>{state.label}</span>
                {#if measureState(row) && measureState(row).status !== 'complete'}<span class="v2-tag is-warn" title={measureState(row).reasons.join(', ')}>{COMPLETENESS_LABEL()[measureState(row).status]}</span>{/if}</span>
              <button type="button" class="v2-dots" aria-label={t('Actions on {name}', { name: target.name })} title={t('Actions on {name}', { name: target.name })} onclick={openMenu(target)}><i class="bi bi-three-dots" aria-hidden="true"></i></button>
            </div>
          {:else}
            <p class="v2-empty">{t('No folder matches.')}</p>
          {/each}
        </div>
        {#if folderRows.length > folderShown}
          <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm sc5__more" onclick={() => (folderShown += 50)}>{t('Show {count} more', { count: Math.min(50, folderRows.length - folderShown) })}</button>
        {/if}
      </div>
    {:else if tab === 'quarantine'}
      <div class="v2-sec">
        <p class="sc5__qinfo"><i class="bi bi-archive" aria-hidden="true"></i>
          {quarantine ? t('{size} in quarantine.', { size: formatBytes(quarantine.quarantine_bytes) }) : ''}
          {quarantine?.purge_days ? t('Copies are deleted for good after {days} days in quarantine.', { days: quarantine.purge_days })
            : t('Nothing is deleted automatically: copies stay until someone restores them (purge set in Settings).')}
          {t('Archived folders are never purged.')}</p>
        <div class="v2-sh">
          <div class="v2-seg" role="group" aria-label={t('State')}>
            {#each [['all', t('All')], ['moved', t('In quarantine')], ['pending', t('In progress')], ['failed', t('Refused')], ['restored', t('Restored')]] as [key, label] (key)}
              <button type="button" class:is-on={quarantineStatus === key} onclick={() => (quarantineStatus = key as typeof quarantineStatus)}>{label}</button>
            {/each}
          </div>
          <div class="v2-seg" role="group" aria-label={t('Kind')}>
            {#each [['all', t('All')], ['duplicate', t('Duplicates')], ['archive', t('Archives')]] as [key, label] (key)}
              <button type="button" class:is-on={quarantineKind === key} onclick={() => (quarantineKind = key as typeof quarantineKind)}>{label}</button>
            {/each}
          </div>
          {#if quarantineRoot}<div class="v2-sh__r"><span class="v2-tag is-info">{roots.find((row) => Number(row.storage_root_id) === quarantineRoot)?.storage_root_name ?? `#${quarantineRoot}`}
            <button type="button" class="b2s-link-btn" onclick={() => (quarantineRoot = null)} aria-label={t('All the folders')}>✕</button></span></div>{/if}
        </div>
        {#if quarantine}<QuarantineList moves={quarantineRows} showFolder={!quarantineRoot} onRestore={restoreMoves} />{:else}<LoadingState block skeleton="rows" rows={4} />{/if}
      </div>
    {:else if tab === 'settings' && isAdmin && form}
      <form class="sc5__form" onsubmit={(event) => { event.preventDefault(); save(); }}>
        <label class="sc5__check"><input type="checkbox" bind:checked={form.schedule_enabled} /> {t('Scan every folder on schedule')}</label>
        {#if form.schedule_enabled}
          <div class="sc5__freq" role="radiogroup" aria-label={t('Frequency')}>
            <label><input type="radio" name="frequency" value="days" bind:group={form.frequency} /> {t('Every N days, at set hours')}</label>
            <label><input type="radio" name="frequency" value="hours" bind:group={form.frequency} /> {t('Every N hours, at any time')}</label>
          </div>
          {#if form.frequency === 'hours'}
            <label>{t('Every (hours)')}<input class="b2s-input" type="number" min="1" max="24" bind:value={form.interval_hours} /></label>
          {:else}
            <label>{t('Every (days, 1 = once a day)')}<input class="b2s-input" type="number" min="1" max="90" bind:value={form.interval_days} /></label>
            <label>{t('Starts at')}<input class="b2s-input" type="time" bind:value={form.window_start} /></label>
            <label>{t('Stops at')}<input class="b2s-input" type="time" bind:value={form.window_end} /></label>
          {/if}
          <p class="sc5__hint sc5__summary">{scheduleText(form)}</p>
        {/if}
        <label>{t('Scans at a time per server')}<input class="b2s-input" type="number" min="1" max="8" bind:value={form.per_server} /></label>
        <label>{t('Full walk every (days)')}<input class="b2s-input" type="number" min="1" max="365" bind:value={form.full_every_days} /></label>
        <label>{t('Fingerprints per piece (duplicates)')}<input class="b2s-input" type="number" min="0" max="500000" step="1000" bind:value={form.hash_files_max} /></label>
        <label class="sc5__check"><input type="checkbox" bind:checked={form.file_owners} />
          {t('Read the NTFS owner of each file (one more read per file: walks take longer)')}</label>
        <fieldset class="sc5__purge">
          <legend>{t('Quarantine of duplicates')}</legend>
          <label class="sc5__check"><input type="radio" name="purge" checked={!form.quarantine_purge_days} onchange={() => form && (form.quarantine_purge_days = 0)} />
            {t('Keep the copies in quarantine until someone restores or deletes them (recommended)')}</label>
          <label class="sc5__check"><input type="radio" name="purge" checked={form.quarantine_purge_days > 0} onchange={() => form && (form.quarantine_purge_days = form.quarantine_purge_days || 90)} />
            {t('Delete them for good after')}
            <input class="b2s-input sc5__days" type="number" min="1" max="3650" disabled={!form.quarantine_purge_days} bind:value={form.quarantine_purge_days} aria-label={t('Days in quarantine before deletion')} /> {t('days')}</label>
          {#if form.quarantine_purge_days > 0}
            <p class="sc5__warn"><i class="bi bi-exclamation-triangle" aria-hidden="true"></i> {t('A purged copy cannot come back. Each copy is checked identical to the copy kept before it moves, and checked again before it is deleted; every purge is written to the audit log.')}</p>
          {/if}
        </fieldset>
        <p class="sc5__hint">{t('Between two full walks, only the sub-folders where the NTFS change journal shows a change are walked again. A server that cannot be walked on (DFS namespace, no WinRM) is measured through SMB by the worker of the core.')}</p>
        <div class="sc5__btns"><button type="submit" class="b2s-btn b2s-btn-primary" disabled={busy}>{t('Save')}</button></div>
      </form>
    {/if}
  {/if}
</section>

<ContextMenu open={menu != null} title={menu?.target.name ?? ''} items={menuItems} at={menu?.at} onClose={() => (menu = null)} {onPick} />

<style>
  .sc5__band { display: flex; flex-wrap: wrap; align-items: center; gap: 24px; padding: 18px 22px; border: 1px solid var(--b2s-color-border); border-radius: 16px; background: var(--b2s-color-surface, #fff); }
  .sc5__states { display: flex; flex-wrap: wrap; gap: 4px; }
  .sc5__qinfo { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .sc5__sched { display: flex; flex-direction: column; gap: 3px; min-width: 260px; }
  .sc5__sched small { color: var(--b2s-color-text-muted); font-size: 11px; font-weight: 600; letter-spacing: 0.09em; text-transform: uppercase; }
  .sc5__sched b { color: var(--b2s-color-text); font-size: 19px; font-weight: 600; }
  .sc5__sched span { color: var(--b2s-color-text-muted); font-size: 13px; }
  .sc5__sched.is-on b::before { content: ''; display: inline-block; width: 9px; height: 9px; margin-right: 8px; border-radius: 50%; background: var(--b2s-accent); vertical-align: 2px; }
  .sc5__stats { flex: 1 1 440px; margin-left: auto; border: 0; }
  .sc5__stats .v2-stat b { font-size: 24px; }
  .sc5__run { grid-template-columns: 120px minmax(0, 1fr) auto; align-items: start; }
  .sc5__run .v2-nm { gap: 4px; }
  .sc5__bar { max-width: 420px; height: 5px; }
  .sc5__err { color: var(--b2s-color-danger-strong); }
  .sc5__end { display: flex; align-items: center; gap: 8px; }
  .sc5__g { grid-template-columns: minmax(220px, 2fr) minmax(130px, 1fr) 100px 110px 130px 140px 36px; min-width: 900px; }
  .sc5__more { align-self: center; }
  .sc5__form { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px 20px; max-width: 980px; }
  .sc5__form label { display: flex; flex-direction: column; gap: 5px; font-size: var(--b2s-fs-sm); font-weight: 500; }
  .sc5__form label.sc5__check { grid-column: 1 / -1; flex-direction: row; align-items: center; gap: 8px; }
  .sc5__freq { grid-column: 1 / -1; display: flex; gap: 18px; }
  .sc5__freq label { flex-direction: row !important; align-items: center; gap: 6px; }
  .sc5__hint { grid-column: 1 / -1; margin: 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .sc5__summary { font-weight: 600; color: var(--b2s-color-text); }
  .sc5__btns { grid-column: 1 / -1; display: flex; justify-content: flex-end; }
  .sc5__purge { grid-column: 1 / -1; display: grid; gap: 8px; margin: 4px 0 0; padding: 12px 14px; border: 1px solid var(--b2s-color-border); border-radius: 12px; }
  .sc5__purge legend { padding: 0 6px; font-size: var(--b2s-fs-sm); font-weight: 600; }
  .sc5__purge .sc5__check { font-weight: 400; }
  .sc5__days { width: 90px; height: 32px; }
  .sc5__warn { margin: 0; color: var(--b2s-color-warning-strong); font-size: var(--b2s-fs-xs); }
</style>
