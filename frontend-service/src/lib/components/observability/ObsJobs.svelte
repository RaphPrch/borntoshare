<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { apiPostData } from '$lib/api/client';
  import { csvFilename, downloadCsv } from '$lib/utils/csv';
  import SearchField from '$lib/components/ui/SearchField.svelte';
  import StatusBadge from '$lib/components/ui/StatusBadge.svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import KpiCard from '$lib/components/ui/KpiCard.svelte';
  import Pagination from '$lib/components/ui/Pagination.svelte';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import EmptyStateInline from '$lib/components/ui/EmptyStateInline.svelte';
  import ConfirmActionModal from '$lib/components/ui/ConfirmActionModal.svelte';
  import Drawer from '$lib/components/ui/Drawer.svelte';
  import { t } from '$lib/i18n';
  import { formatDateTime, timeAgo } from '$lib/utils/format';
  import {
    cancelAdminJob,
    flushAdminJobs,
    getAdminJob,
    listAdminJobs,
    retryAdminJob,
    type AdminJobDetail,
    type AdminProvisioningJob
  } from '$lib/api/admin-jobs';
  import { toast } from '$lib/stores/toast';
  import { reportUiError } from '$lib/errors';
  import { formatSeconds, isActiveJob, jobOriginLabel, jobStatusLabel, jobStatusVariant, jobTypeLabel, normalizeJobStatus } from '$lib/utils/jobs';

  /** Opened from the overview: « FAILED » or « stuck » */
  export let initialStatus: string = 'all';

  const POLL_INTERVAL_MS = 5000;
  type Job = AdminProvisioningJob;

  let jobs: Job[] = [];
  let loading = true;
  let loadError: string | null = null;
  let query = '';
  let statusFilter = initialStatus || 'all';
  let typeFilter = 'all';
  let targetFilter = 'all';
  // The health checks run every few minutes: hidden unless asked, they would bury the rest
  let showRoutine = false;
  let page = 1;
  let pageSize = 25;
  let busy = false;
  let cancelling: Job | null = null;
  let flushing: Job[] | null = null;
  let detail: AdminJobDetail | null = null;
  let detailId: number | null = null;
  let detailLoading = false;
  let timer: ReturnType<typeof setInterval> | null = null;

  const TARGET_ICON: Record<string, string> = { folder: 'bi-folder2', server: 'bi-hdd-network', directory: 'bi-diagram-3', host: 'bi-pc-display' };
  const stuckLabel = (job: Job) => (job.stuck === 'running' ? t('Running far too long') : t('Stuck in the queue'));
  const statusText = (job: Job) => (job.stuck ? stuckLabel(job) : jobStatusLabel(job.status));
  const statusTone = (job: Job) => (job.stuck ? 'warning' : jobStatusVariant(job.status));
  const errorText = (job: Job) => job.error_message || job.error_code || '';

  async function refresh(silent = false) {
    if (!silent) loadError = null;
    try {
      jobs = (await listAdminJobs(fetch, { limit: 500, exclude_job_type: showRoutine ? undefined : 'INFRA_HEALTH' })) ?? [];
      // The open job is followed while it runs (a finished one no longer changes)
      if (detailId && silent && detail && isActiveJob(detail.status)) void openDetail(detailId, true);
    } catch (error: unknown) {
      if (!silent) loadError = reportUiError(error, t('Unable to load jobs'), 'observability.jobs.refresh');
    } finally {
      loading = false;
    }
  }

  async function openDetail(id: number, silent = false) {
    detailId = id;
    if (!silent) {
      detailLoading = true;
      detail = null;
    }
    try {
      const value = await getAdminJob(fetch, id);
      if (detailId === id) detail = value;
    } catch (error: unknown) {
      if (!silent) reportUiError(error, t('Unable to load job #{jobId}', { jobId: id }), 'observability.jobs.detail');
    } finally {
      detailLoading = false;
    }
  }
  function closeDetail() {
    detailId = null;
    detail = null;
  }

  async function retry(job: Job) {
    busy = true;
    try {
      const result = await retryAdminJob(fetch, Number(job.id));
      toast.success(result?.reused
        ? t('The same task is already running: job #{jobId}', { jobId: result.job_id ?? '' })
        : t('Job #{old} started again: job #{jobId}', { old: job.id, jobId: result?.job_id ?? '' }));
      await refresh(true);
      if (result?.job_id && detailId) void openDetail(Number(result.job_id));
    } catch (error: unknown) {
      reportUiError(error, t('Unable to start job #{jobId} again', { jobId: job.id }), 'observability.jobs.retry');
    } finally {
      busy = false;
    }
  }

  // Every failure shown (filters applied) that can be retried, one after the other
  let retryingAll = false;
  async function retryShown() {
    const targets = filtered.filter((job) => job.retryable);
    if (!targets.length || retryingAll) return;
    retryingAll = true;
    let ok = 0;
    const failed: string[] = [];
    for (const job of targets) {
      try {
        await retryAdminJob(fetch, Number(job.id));
        ok += 1;
      } catch (error: unknown) {
        failed.push(`#${job.id}`);
      }
    }
    retryingAll = false;
    if (ok) toast.success(t('{count} job(s) started again', { count: ok }));
    if (failed.length) toast.error(t('Not started again: {ids}', { ids: failed.join(', ') }));
    await refresh(true);
  }

  // A measure of the 5S scanner: stopped through its folder (the module closes it, the scanner stops before its next batch)
  async function stopFives(job: Job) {
    busy = true;
    try {
      await apiPostData(fetch, `/storage-roots/${job.target?.id}/stop`, { kind: 'measure' });
      toast.success(t('Measure stopped'));
      await refresh(true);
    } catch (error: unknown) {
      reportUiError(error, t('Unable to stop the measure'), 'observability.jobs.stop-5s');
    } finally {
      busy = false;
    }
  }

  async function confirmCancel() {
    const job = cancelling;
    cancelling = null;
    if (!job) return;
    busy = true;
    try {
      await cancelAdminJob(fetch, Number(job.id), { reason: 'Stopped by an operator from Observability › Jobs', source: 'ui' });
      toast.success(t('Job #{jobId} canceled', { jobId: job.id }));
      await refresh(true);
    } catch (error: unknown) {
      reportUiError(error, t('Unable to cancel job #{jobId}', { jobId: job.id }), 'observability.jobs.cancel');
    } finally {
      busy = false;
    }
  }

  async function confirmFlush() {
    const list = flushing;
    flushing = null;
    if (!list?.length) return;
    busy = true;
    try {
      const result = await flushAdminJobs(fetch, list.map((job) => Number(job.id)));
      const done = result?.flushed?.length ?? 0;
      if (done) toast.success(t('{count} stuck job(s) flushed', { count: done }));
      if (result?.failed?.length) toast.error(t('{count} job(s) could not be flushed: {message}', { count: result.failed.length, message: result.failed[0].message }));
      if (!done && !result?.failed?.length) toast.info(t('Nothing to flush: the jobs moved on in the meantime.'));
      await refresh(true);
    } catch (error: unknown) {
      reportUiError(error, t('Unable to flush the stuck jobs'), 'observability.jobs.flush');
    } finally {
      busy = false;
    }
  }

  async function copy(value: string) {
    try {
      await navigator.clipboard.writeText(value);
      toast.success(t('Copied'));
    } catch {
      toast.error(t('Unable to copy'));
    }
  }

  onMount(() => {
    void refresh();
    timer = setInterval(() => void refresh(true), POLL_INTERVAL_MS);
  });
  onDestroy(() => {
    if (timer) clearInterval(timer);
  });

  const exportJobs = () =>
    downloadCsv(csvFilename('jobs'), [
      { header: 'ID', value: (job: Job) => job.id },
      { header: t('Status'), value: (job: Job) => statusText(job) },
      { header: t('Task'), value: (job: Job) => jobTypeLabel(job.job_type, job.action) },
      { header: t('Type'), value: (job: Job) => job.job_type },
      { header: t('Action'), value: (job: Job) => job.action },
      { header: t('Target'), value: (job: Job) => job.target?.label ?? '' },
      { header: t('Origin'), value: (job: Job) => jobOriginLabel(job.origin) },
      { header: t('Requested by'), value: (job: Job) => job.requested_by ?? '' },
      { header: t('Created'), value: (job: Job) => formatDateTime(job.created_at) },
      { header: t('Started'), value: (job: Job) => formatDateTime(job.started_at) },
      { header: t('Finished'), value: (job: Job) => formatDateTime(job.finished_at) },
      { header: t('Wait (s)'), value: (job: Job) => job.wait_seconds ?? '' },
      { header: t('Duration (s)'), value: (job: Job) => job.run_seconds ?? '' },
      { header: t('Attempts'), value: (job: Job) => job.attempts ?? 1 },
      { header: t('Error code'), value: (job: Job) => job.error_code },
      { header: t('Error'), value: (job: Job) => job.error_message },
      { header: t('Correlation ID'), value: (job: Job) => job.correlation_id }
    ], filtered);

  const median = (values: number[]) => {
    if (!values.length) return null;
    const sorted = [...values].sort((a, b) => a - b);
    return sorted[Math.floor(sorted.length / 2)];
  };
  const dayAgo = () => Date.now() - 24 * 3600 * 1000;
  const recent = (job: Job) => new Date(String(job.created_at ?? '').replace(' ', 'T') + (String(job.created_at ?? '').endsWith('Z') ? '' : 'Z')).getTime() >= dayAgo();

  $: stuckJobs = jobs.filter((job) => Boolean(job.stuck));
  $: last24 = jobs.filter(recent);
  $: counts = {
    active: jobs.filter((job) => isActiveJob(job.status) && !job.stuck).length,
    failed: last24.filter((job) => normalizeJobStatus(job.status) === 'FAILED').length,
    stuck: stuckJobs.length,
    succeeded: last24.filter((job) => normalizeJobStatus(job.status) === 'SUCCEEDED').length,
    retryable: jobs.filter((job) => job.retryable && normalizeJobStatus(job.status) === 'FAILED').length
  };
  $: finished24 = counts.failed + counts.succeeded;
  $: failureRate = finished24 ? Math.round((counts.failed / finished24) * 100) : null;
  $: medianRun = median(last24.filter((job) => normalizeJobStatus(job.status) === 'SUCCEEDED' && job.run_seconds != null).map((job) => Number(job.run_seconds)));
  $: typesPresent = [...new Set(jobs.map((job) => `${job.job_type ?? ''}|${job.action ?? ''}`))]
    .map((key) => ({ key, label: jobTypeLabel(key.split('|')[0], key.split('|')[1]) }))
    .sort((a, b) => a.label.localeCompare(b.label));
  $: targetsPresent = [...new Set(jobs.map((job) => job.target?.kind).filter(Boolean))] as string[];
  $: filtered = jobs
    .filter((job) => {
      const s = normalizeJobStatus(job.status);
      if (statusFilter === 'all') return true;
      if (statusFilter === 'active') return isActiveJob(s);
      if (statusFilter === 'stuck') return Boolean(job.stuck);
      if (statusFilter === 'retryable') return Boolean(job.retryable);
      return s === statusFilter;
    })
    .filter((job) => typeFilter === 'all' || `${job.job_type ?? ''}|${job.action ?? ''}` === typeFilter)
    .filter((job) => targetFilter === 'all' || job.target?.kind === targetFilter)
    .filter((job) => {
      const q = query.trim().toLowerCase();
      if (!q) return true;
      return [job.id, job.correlation_id, jobTypeLabel(job.job_type, job.action), job.job_type, job.action, job.error_code, job.error_message,
        job.target?.label, job.target?.detail, jobOriginLabel(job.origin), job.requested_by]
        .map((v) => String(v ?? '').toLowerCase())
        .join(' ')
        .includes(q);
    })
    // Newest first (the measures of the 5S scanner, listed with negative ids, are mixed in by date)
    .sort((a, b) => String(b.created_at ?? '').localeCompare(String(a.created_at ?? '')) || Number(b.id) - Number(a.id));
  $: query, statusFilter, typeFilter, targetFilter, (page = 1);
  $: retryableShown = filtered.filter((job) => job.retryable).length;
  $: pageRows = filtered.slice((page - 1) * pageSize, page * pageSize);
  /** The share of its timeout a running job has used (the bar under its duration) */
  const timeoutShare = (job: Job) =>
    job.run_seconds != null && job.timeout_seconds ? Math.min(100, Math.round((Number(job.run_seconds) / Number(job.timeout_seconds)) * 100)) : null;
  const pretty = (value: unknown) => JSON.stringify(value, null, 2);
  const hasKeys = (value: unknown) => Boolean(value && typeof value === 'object' && Object.keys(value as object).length);
  const TARGET_LABEL = (): Record<string, string> => ({ folder: t('Folders'), server: t('File servers'), directory: t('Directories'), host: t('Hosts') });
</script>

<div class="obs-jobs">
  <section class="b2s-kpi-grid" aria-label={t('Jobs summary')}>
    <KpiCard label={t('Running or queued')} value={counts.active} icon="bi-arrow-repeat" tone="info" />
    <KpiCard label={t('Stuck')} value={counts.stuck} icon="bi-hourglass-split" tone={counts.stuck ? 'warning' : 'neutral'}
      hint={counts.stuck ? t('Flush them to free their folder or server') : t('None')} />
    <KpiCard label={t('Failed (24 h)')} value={counts.failed} icon="bi-x-octagon" tone={counts.failed ? 'danger' : 'neutral'}
      hint={failureRate == null ? null : t('{rate} % of the finished jobs', { rate: failureRate })} />
    <KpiCard label={t('Succeeded (24 h)')} value={counts.succeeded} icon="bi-check2-circle" tone="success"
      hint={medianRun == null ? null : t('Median duration {duration}', { duration: formatSeconds(medianRun) })} />
  </section>

  {#if counts.stuck}
    <InlineAlert tone="warning">
      <div class="obs-banner">
        <span>{t('{count} job(s) are stuck: nobody took them, or they run far beyond their timeout. Their folder or server waits for them.', { count: counts.stuck })}</span>
        <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-secondary" disabled={busy} on:click={() => (flushing = stuckJobs)}>
          <i class="bi bi-trash3" aria-hidden="true"></i>{t('Flush the stuck jobs')}
        </button>
      </div>
    </InlineAlert>
  {/if}

  <div class="b2s-toolbar">
    <SearchField wrapperClass="b2s-toolbar__search" placeholder={t('Search a job, a folder, an error…')} ariaLabel={t('Filter jobs')} bind:value={query} />
    <select class="b2s-select" bind:value={statusFilter} aria-label={t('Status')}>
      <option value="all">{t('All statuses')}</option>
      <option value="active">{t('Running or queued')}</option>
      <option value="stuck">{t('Stuck')}</option>
      <option value="FAILED">{t('Failed')}</option>
      <option value="retryable">{t('Can be started again')}</option>
      <option value="SUCCEEDED">{t('Succeeded')}</option>
      <option value="CANCELLED">{t('Cancelled')}</option>
    </select>
    <select class="b2s-select" bind:value={typeFilter} aria-label={t('Task')}>
      <option value="all">{t('All tasks')}</option>
      {#each typesPresent as type (type.key)}<option value={type.key}>{type.label}</option>{/each}
    </select>
    <select class="b2s-select" bind:value={targetFilter} aria-label={t('Target')}>
      <option value="all">{t('All targets')}</option>
      {#each targetsPresent as kind (kind)}<option value={kind}>{TARGET_LABEL()[kind] ?? kind}</option>{/each}
    </select>
    <label class="obs-toggle">
      <input type="checkbox" bind:checked={showRoutine} on:change={() => refresh(false)} />
      {t('Automatic health checks')}
    </label>
    {#if retryableShown}
      <button type="button" class="b2s-btn b2s-btn-secondary b2s-toolbar__end" disabled={busy || retryingAll} on:click={retryShown}
        title={t('Start again the failed or stopped checks and scans shown')}>
        <i class="bi bi-arrow-counterclockwise" aria-hidden="true"></i>{t('Retry the {count} shown', { count: retryableShown })}
      </button>
    {/if}
    <button type="button" class="b2s-btn b2s-btn-secondary" class:b2s-toolbar__end={!retryableShown} on:click={exportJobs} disabled={filtered.length === 0}>
      <i class="bi bi-download" aria-hidden="true"></i>{t('Export CSV')}
    </button>
    <button type="button" class="b2s-btn b2s-btn-secondary" on:click={() => refresh(false)} disabled={busy}>
      <i class="bi bi-arrow-clockwise" aria-hidden="true"></i>{t('Refresh')}
    </button>
  </div>

  {#if loadError}
    <InlineAlert tone="error">{loadError}</InlineAlert>
  {/if}

  <section class="b2s-card obs-card">
    {#if loading}
      <LoadingState skeleton="rows" />
    {:else if filtered.length === 0}
      <EmptyStateInline message={t('No job found.')} />
    {:else}
      <div class="b2s-table-wrap">
        <table class="b2s-table obs-table">
          <thead>
            <tr>
              <th>{t('Status')}</th>
              <th>{t('Task')}</th>
              <th>{t('Target')}</th>
              <th>{t('Origin')}</th>
              <th>{t('Created')}</th>
              <th class="obs-num">{t('Wait')}</th>
              <th class="obs-num">{t('Duration')}</th>
              <th>{t('Error')}</th>
              <th class="obs-actions-col"><span class="visually-hidden">{t('Actions')}</span></th>
            </tr>
          </thead>
          <tbody>
            {#each pageRows as job (job.id)}
              {@const share = isActiveJob(job.status) ? timeoutShare(job) : null}
              <tr class="obs-row" class:is-open={detailId === Number(job.id)} on:click={() => !job.external && openDetail(Number(job.id))}>
                <td>
                  <StatusBadge compact label={statusText(job)} variant={statusTone(job)} />
                  {#if Number(job.attempts ?? 1) > 1}<small class="obs-sub">{t('Attempt {n}', { n: job.attempts ?? 1 })}</small>{/if}
                </td>
                <td class="obs-main">
                  <strong>{jobTypeLabel(job.job_type, job.action)}</strong>
                  <small class="mono">{job.external ? `5S · ${job.correlation_id}` : `#${job.id} · ${job.action ?? job.job_type}`}</small>
                  {#if job.progress?.chunks_total && isActiveJob(job.status)}<small class="obs-sub">{t('Scan {done}/{total} · {files} file(s)', { done: job.progress.chunks_done, total: job.progress.chunks_total, files: Number(job.progress.files ?? 0).toLocaleString('fr-FR') })}</small>{/if}
                </td>
                <td class="obs-target">
                  {#if job.target}
                    <i class={`bi ${TARGET_ICON[job.target.kind] ?? 'bi-bullseye'}`} aria-hidden="true"></i>
                    {#if job.target.href}<a href={job.target.href} on:click|stopPropagation>{job.target.label}</a>{:else}<span>{job.target.label}</span>{/if}
                    {#if job.target.detail}<small class="obs-sub">{job.target.detail}</small>{/if}
                  {:else}—{/if}
                </td>
                <td class="obs-origin">
                  {jobOriginLabel(job.origin)}
                  {#if job.requested_by}<small class="obs-sub"><i class="bi bi-person" aria-hidden="true"></i> {job.requested_by}</small>{/if}
                  {#if job.retry_of}<small class="obs-sub">{t('retry of #{id}', { id: job.retry_of })}</small>{/if}
                </td>
                <td class="obs-date" title={formatDateTime(job.created_at)}>{timeAgo(job.created_at)}</td>
                <td class="obs-num" class:is-long={Number(job.wait_seconds ?? 0) > 60}>{formatSeconds(job.wait_seconds)}</td>
                <td class="obs-num">
                  {formatSeconds(job.run_seconds)}
                  {#if share != null}
                    <span class="obs-bar" class:is-over={share >= 100} title={t('{share} % of its {timeout} timeout', { share, timeout: formatSeconds(job.timeout_seconds) })}>
                      <span style={`width:${share}%`}></span>
                    </span>
                  {/if}
                </td>
                <td class="obs-error">
                  {#if errorText(job)}<span title={String(job.error_code ?? '')}>{errorText(job)}</span>{:else}—{/if}
                </td>
                <td class="obs-actions" on:click|stopPropagation>
                  {#if job.retryable}
                    <button class="b2s-btn b2s-btn-sm b2s-btn-secondary" type="button" disabled={busy} on:click={() => retry(job)} title={t('Start it again with the same parameters')}>
                      <i class="bi bi-arrow-counterclockwise" aria-hidden="true"></i>{t('Retry')}
                    </button>
                  {/if}
                  {#if job.external}
                    {#if isActiveJob(job.status) && job.target?.id}
                      <button class="b2s-btn b2s-btn-sm b2s-btn-danger-outline" type="button" disabled={busy} on:click={() => stopFives(job)}>{t('Stop')}</button>
                    {/if}
                  {:else if job.stuck}
                    <button class="b2s-btn b2s-btn-sm b2s-btn-danger-outline" type="button" disabled={busy} on:click={() => (flushing = [job])}>{t('Flush')}</button>
                  {:else if isActiveJob(job.status)}
                    <button class="b2s-btn b2s-btn-sm b2s-btn-danger-outline" type="button" disabled={busy} on:click={() => (cancelling = job)}>{t('Stop')}</button>
                  {/if}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
      <Pagination total={filtered.length} bind:page bind:pageSize />
    {/if}
  </section>
</div>

<Drawer
  open={detailId != null}
  onClose={closeDetail}
  size="lg"
  iconClass="bi bi-cpu"
  title={detail ? jobTypeLabel(detail.job_type, detail.action) : t('Job #{jobId}', { jobId: detailId ?? '' })}
  subtitle={detail ? `#${detail.id} · ${detail.job_type ?? ''} · ${detail.action ?? ''}` : ''}
>
  {#if detailLoading && !detail}
    <LoadingState skeleton="rows" />
  {:else if detail}
    <div class="jd">
      <div class="jd__status">
        <StatusBadge label={statusText(detail)} variant={statusTone(detail)} />
        {#if detail.stuck}<span class="jd__hint">{detail.stuck === 'running'
          ? t('Running for {run}, its timeout is {timeout}.', { run: formatSeconds(detail.run_seconds), timeout: formatSeconds(detail.timeout_seconds) })
          : t('Waiting for {wait} without a worker taking it.', { wait: formatSeconds(detail.wait_seconds) })}</span>{/if}
      </div>

      {#if errorText(detail)}
        <InlineAlert tone="error">
          <strong>{detail.error_code ?? t('Error')}</strong> — {detail.error_message ?? ''}
        </InlineAlert>
      {/if}
      {#if !detail.retryable && detail.retry_elsewhere && normalizeJobStatus(detail.status) === 'FAILED'}
        <InlineAlert tone="info">{t('This task is tied to what asked for it: start it again from {place}.', { place: t(detail.retry_elsewhere) })}</InlineAlert>
      {/if}

      <section class="jd__section">
        <h3>{t('Timeline')}</h3>
        <ol class="jd__timeline">
          <li class="is-done"><span>{t('Created')}</span><b>{formatDateTime(detail.created_at)}</b></li>
          <li class:is-done={Boolean(detail.started_at)}>
            <span>{t('Taken by a worker')}</span>
            <b>{detail.started_at ? formatDateTime(detail.started_at) : t('not yet')}</b>
            <small>{t('waited {wait}', { wait: formatSeconds(detail.wait_seconds) })}</small>
          </li>
          <li class:is-done={Boolean(detail.finished_at)}>
            <span>{t('Finished')}</span>
            <b>{detail.finished_at ? formatDateTime(detail.finished_at) : isActiveJob(detail.status) ? t('running') : '—'}</b>
            {#if detail.run_seconds != null}<small>{t('ran {run} (timeout {timeout})', { run: formatSeconds(detail.run_seconds), timeout: formatSeconds(detail.timeout_seconds) })}</small>{/if}
          </li>
        </ol>
      </section>

      <section class="jd__section">
        <h3>{t('Summary')}</h3>
        <dl class="jd__grid">
          <dt>{t('Target')}</dt>
          <dd>
            {#if detail.target}
              {#if detail.target.href}<a href={detail.target.href}>{detail.target.label}</a>{:else}{detail.target.label}{/if}
              {#if detail.target.detail}<small> · {detail.target.detail}</small>{/if}
            {:else}—{/if}
          </dd>
          <dt>{t('Origin')}</dt><dd>{jobOriginLabel(detail.origin)}</dd>
          <dt>{t('Requested by')}</dt><dd>{detail.requested_by ?? t('the platform (schedule, policy or worker)')}</dd>
          <dt>{t('Worker queue')}</dt><dd class="mono">{detail.queue ?? '—'}</dd>
          <dt>{t('Attempts')}</dt><dd>{detail.attempts ?? 1}{#if Number(detail.watchdog_republish_count ?? 0) > 0} · {t('sent again {n} time(s) by the watchdog', { n: detail.watchdog_republish_count ?? 0 })}{/if}</dd>
          {#if detail.retry_of}<dt>{t('Retry of')}</dt><dd><button type="button" class="jd__link" on:click={() => openDetail(Number(detail?.retry_of))}>#{detail.retry_of}</button></dd>{/if}
          {#if detail.retried_by?.length}
            <dt>{t('Started again as')}</dt>
            <dd>{#each detail.retried_by as id, index (id)}{#if index}, {/if}<button type="button" class="jd__link" on:click={() => openDetail(Number(id))}>#{id}</button>{/each}</dd>
          {/if}
          <dt>{t('Correlation ID')}</dt>
          <dd class="mono jd__copy">{detail.correlation_id ?? '—'}
            {#if detail.correlation_id}<button type="button" class="jd__icon" title={t('Copy')} aria-label={t('Copy')} on:click={() => copy(String(detail?.correlation_id))}><i class="bi bi-copy" aria-hidden="true"></i></button>{/if}
          </dd>
        </dl>
      </section>

      {#if hasKeys(detail.result)}
        <section class="jd__section">
          <h3>{t('Result')}</h3>
          {#if detail.result.message}<p class="jd__message">{String(detail.result.message)}</p>{/if}
          <details><summary>{t('Full answer of the worker')}</summary><pre>{pretty(detail.result)}</pre></details>
        </section>
      {/if}
      {#if hasKeys(detail.error)}
        <section class="jd__section">
          <h3>{t('Error details')}</h3>
          <pre>{pretty(detail.error)}</pre>
        </section>
      {/if}
      <section class="jd__section">
        <h3>{t('Parameters')}</h3>
        <p class="jd__hint">{t('What the job was given; secrets are hidden (a secret reference is not a secret).')}</p>
        <details open={!hasKeys(detail.result)}><summary>{t('Show the parameters')}</summary><pre>{pretty(detail.payload)}</pre></details>
      </section>
      {#if hasKeys(detail.metrics)}
        <section class="jd__section">
          <h3>{t('Metrics')}</h3>
          <pre>{pretty(detail.metrics)}</pre>
        </section>
      {/if}
    </div>
  {/if}

  <svelte:fragment slot="footer">
    {#if detail}
      {#if detail.stuck}
        <button type="button" class="b2s-btn b2s-btn-danger-outline" disabled={busy} on:click={() => detail && (flushing = [detail])}>{t('Flush')}</button>
      {:else if isActiveJob(detail.status)}
        <button type="button" class="b2s-btn b2s-btn-danger-outline" disabled={busy} on:click={() => (cancelling = detail)}>{t('Stop')}</button>
      {/if}
      {#if detail.retryable}
        <button type="button" class="b2s-btn b2s-btn-primary" disabled={busy} on:click={() => detail && retry(detail)}>
          <i class="bi bi-arrow-counterclockwise" aria-hidden="true"></i>{t('Retry')}
        </button>
      {/if}
    {/if}
    <button type="button" class="b2s-btn b2s-btn-secondary" on:click={closeDetail}>{t('Close')}</button>
  </svelte:fragment>
</Drawer>

<ConfirmActionModal
  open={!!cancelling}
  title={t('Stop the job')}
  subtitle={t('Job #{id} is cancelled; the worker skips it if it has not started yet.', { id: cancelling?.id ?? '' })}
  confirmLabel={t('Stop')}
  onConfirm={confirmCancel}
  onClose={() => (cancelling = null)}
/>

<ConfirmActionModal
  open={!!flushing}
  title={t('Flush the stuck jobs')}
  subtitle={flushing?.length === 1
    ? t('Job #{id} is closed as failed: the worker skips it and its folder or server no longer waits for it. It can then be started again.', { id: flushing[0].id })
    : t('{count} jobs are closed as failed: the worker skips them and their folder or server no longer waits for them. They can then be started again.', { count: flushing?.length ?? 0 })}
  confirmLabel={t('Flush')}
  onConfirm={confirmFlush}
  onClose={() => (flushing = null)}
/>

<style>
  .obs-jobs {
    display: grid;
    gap: 16px;
  }
  .obs-card {
    overflow: hidden;
  }
  .obs-banner {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }
  .obs-toggle {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: var(--b2s-fs-sm);
    color: var(--b2s-color-text-muted);
    white-space: nowrap;
  }
  .obs-row {
    cursor: pointer;
  }
  .obs-row:hover td,
  .obs-row.is-open td {
    background: var(--b2s-color-surface-hover, rgba(0, 0, 0, 0.03));
  }
  .obs-main strong {
    display: block;
    font-weight: 600;
  }
  .obs-main small,
  .obs-sub {
    display: block;
    margin-top: 2px;
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-xs);
  }
  .obs-target i {
    margin-right: 4px;
    color: var(--b2s-color-text-muted);
  }
  .obs-origin {
    font-size: var(--b2s-fs-sm);
  }
  .mono {
    font-family: var(--b2s-font-mono);
    font-size: var(--b2s-fs-xs);
  }
  .obs-date,
  .obs-num {
    white-space: nowrap;
  }
  .obs-num {
    text-align: right;
    font-variant-numeric: tabular-nums;
  }
  .obs-num.is-long {
    color: var(--b2s-color-warning-strong, #b54708);
  }
  .obs-bar {
    display: block;
    height: 4px;
    margin-top: 4px;
    border-radius: 2px;
    background: var(--b2s-color-border);
    overflow: hidden;
  }
  .obs-bar span {
    display: block;
    height: 100%;
    border-radius: 2px;
    background: var(--b2s-color-info, #2563eb);
  }
  .obs-bar.is-over span {
    background: var(--b2s-color-warning, #d97706);
  }
  .obs-error {
    max-width: 360px;
    color: var(--b2s-color-danger-strong);
    font-size: var(--b2s-fs-sm);
  }
  .obs-error span {
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .obs-actions {
    white-space: nowrap;
    text-align: right;
  }
  .obs-actions .b2s-btn + .b2s-btn {
    margin-left: 6px;
  }
  .obs-actions-col {
    width: 1%;
  }

  .jd {
    display: grid;
    gap: 18px;
  }
  .jd__status {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
  }
  .jd__hint {
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-sm);
  }
  .jd__section h3 {
    margin: 0 0 8px;
    font-size: var(--b2s-fs-sm);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--b2s-color-text-muted);
  }
  .jd__timeline {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    gap: 10px;
  }
  .jd__timeline li {
    position: relative;
    display: grid;
    grid-template-columns: 160px minmax(0, 1fr);
    column-gap: 12px;
    padding-left: 20px;
    color: var(--b2s-color-text-muted);
  }
  .jd__timeline li::before {
    content: '';
    position: absolute;
    left: 0;
    top: 5px;
    width: 10px;
    height: 10px;
    border-radius: 50%;
    border: 2px solid var(--b2s-color-border);
    background: var(--b2s-color-surface, #fff);
  }
  .jd__timeline li.is-done {
    color: inherit;
  }
  .jd__timeline li.is-done::before {
    border-color: var(--b2s-color-primary, #2563eb);
    background: var(--b2s-color-primary, #2563eb);
  }
  .jd__timeline b {
    font-weight: 500;
  }
  .jd__timeline small {
    grid-column: 2;
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-xs);
  }
  .jd__grid {
    display: grid;
    grid-template-columns: 160px minmax(0, 1fr);
    gap: 6px 12px;
    margin: 0;
    font-size: var(--b2s-fs-sm);
  }
  .jd__grid dt {
    color: var(--b2s-color-text-muted);
  }
  .jd__grid dd {
    margin: 0;
    overflow-wrap: anywhere;
  }
  .jd__copy {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .jd__icon,
  .jd__link {
    border: 0;
    background: none;
    padding: 0;
    color: var(--b2s-color-primary, #2563eb);
    cursor: pointer;
  }
  .jd__link {
    font: inherit;
    text-decoration: underline;
  }
  .jd__message {
    margin: 0 0 6px;
  }
  .jd pre {
    margin: 6px 0 0;
    max-height: 320px;
    overflow: auto;
    padding: 10px 12px;
    border-radius: var(--b2s-radius-md, 8px);
    background: var(--b2s-color-surface-muted, #f6f7f9);
    font-family: var(--b2s-font-mono);
    font-size: var(--b2s-fs-xs);
    white-space: pre-wrap;
    word-break: break-word;
  }
  .jd summary {
    cursor: pointer;
    font-size: var(--b2s-fs-sm);
    color: var(--b2s-color-primary, #2563eb);
  }
</style>
