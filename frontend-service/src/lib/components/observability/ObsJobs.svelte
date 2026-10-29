<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { csvFilename, downloadCsv } from '$lib/utils/csv';
  import SearchField from '$lib/components/ui/SearchField.svelte';
  import StatusBadge from '$lib/components/ui/StatusBadge.svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import KpiCard from '$lib/components/ui/KpiCard.svelte';
  import Pagination from '$lib/components/ui/Pagination.svelte';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import EmptyStateInline from '$lib/components/ui/EmptyStateInline.svelte';
  import ConfirmActionModal from '$lib/components/ui/ConfirmActionModal.svelte';
  import { t } from '$lib/i18n';
  import { formatDateTime, timeAgo } from '$lib/utils/format';
  import { cancelAdminJob, listAdminJobs, type AdminProvisioningJob } from '$lib/api/admin-jobs';
  import { toast } from '$lib/stores/toast';
  import { reportUiError } from '$lib/errors';
  import { JOB_TYPES, isActiveJob, jobStatusLabel, jobStatusVariant, jobTypeLabel, normalizeJobStatus } from '$lib/utils/jobs';

  /** Opened from the overview: « failed » or « stuck » */
  export let initialStatus: string = 'all';

  const POLL_INTERVAL_MS = 5000;
  const STUCK_SECONDS = 300;

  let jobs: AdminProvisioningJob[] = [];
  let loading = true;
  let loadError: string | null = null;
  let query = '';
  let statusFilter = initialStatus || 'all';
  let typeFilter = 'all';
  let page = 1;
  let pageSize = 25;
  let busy = false;
  let cancelling: AdminProvisioningJob | null = null;
  let timer: ReturnType<typeof setInterval> | null = null;

  const isStuck = (job: AdminProvisioningJob) =>
    ['QUEUED', 'RETRYING'].includes(normalizeJobStatus(job.status)) && Number(job.queue_age_seconds ?? 0) > STUCK_SECONDS;

  /** The object a job worked on, when the platform has a page for it */
  const objectLink = (job: AdminProvisioningJob): { label: string; href: string } | null => {
    if (job.identity_source_id) return { label: t('Identity source #{id}', { id: job.identity_source_id }), href: '/admin/identity-sources' };
    if (String(job.job_type ?? '').toUpperCase() === 'INFRA_HEALTH') return { label: t('Platform health'), href: '/observability?tab=health' };
    return null;
  };

  async function refresh(silent = false) {
    if (!silent) loadError = null;
    try {
      jobs = (await listAdminJobs(fetch, { limit: 200 })) ?? [];
    } catch (error: unknown) {
      if (!silent) loadError = reportUiError(error, t('Unable to load jobs'), 'observability.jobs.refresh');
    } finally {
      loading = false;
    }
  }

  async function confirmCancel() {
    const job = cancelling;
    cancelling = null;
    if (!job) return;
    busy = true;
    try {
      await cancelAdminJob(fetch, Number(job.id), { reason: 'Cancelled by operator from Observability › Jobs', source: 'ui' });
      toast.success(t('Job #{jobId} canceled', { jobId: job.id }));
      await refresh(true);
    } catch (error: unknown) {
      reportUiError(error, t('Unable to cancel job #{jobId}', { jobId: job.id }), 'observability.jobs.cancel');
    } finally {
      busy = false;
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
      { header: 'ID', value: (job: AdminProvisioningJob) => job.id },
      { header: t('Status'), value: (job: AdminProvisioningJob) => jobStatusLabel(job.status) },
      { header: t('Task'), value: (job: AdminProvisioningJob) => jobTypeLabel(job.job_type, job.action) },
      { header: t('Type'), value: (job: AdminProvisioningJob) => job.job_type },
      { header: t('Updated'), value: (job: AdminProvisioningJob) => formatDateTime(job.updated_at ?? job.created_at) },
      { header: t('Error code'), value: (job: AdminProvisioningJob) => job.error_code },
      { header: t('Error'), value: (job: AdminProvisioningJob) => job.error_message },
      { header: t('Correlation ID'), value: (job: AdminProvisioningJob) => job.correlation_id }
    ], filtered);

  $: counts = {
    active: jobs.filter((j) => isActiveJob(j.status)).length,
    failed: jobs.filter((j) => normalizeJobStatus(j.status) === 'FAILED').length,
    stuck: jobs.filter(isStuck).length,
    succeeded: jobs.filter((j) => normalizeJobStatus(j.status) === 'SUCCEEDED').length
  };
  $: typesPresent = JOB_TYPES.filter((type) => jobs.some((j) => String(j.job_type ?? '').toUpperCase() === type));
  $: filtered = jobs
    .filter((job) => {
      const s = normalizeJobStatus(job.status);
      if (statusFilter === 'all') return true;
      if (statusFilter === 'active') return isActiveJob(s);
      if (statusFilter === 'stuck') return isStuck(job);
      return s === statusFilter;
    })
    .filter((job) => typeFilter === 'all' || String(job.job_type ?? '').toUpperCase() === typeFilter)
    .filter((job) => {
      const q = query.trim().toLowerCase();
      if (!q) return true;
      return [job.id, job.correlation_id, jobTypeLabel(job.job_type, job.action), job.job_type, job.error_code, job.error_message]
        .map((v) => String(v ?? '').toLowerCase())
        .join(' ')
        .includes(q);
    })
    .sort((a, b) => String(b.updated_at ?? b.created_at ?? '').localeCompare(String(a.updated_at ?? a.created_at ?? '')));
  $: query, statusFilter, typeFilter, (page = 1);
  $: pageRows = filtered.slice((page - 1) * pageSize, page * pageSize);
</script>

<div class="obs-jobs">
  <section class="b2s-kpi-grid" aria-label={t('Jobs summary')}>
    <KpiCard label={t('Running or queued')} value={counts.active} icon="bi-arrow-repeat" tone="info" />
    <KpiCard label={t('Failed')} value={counts.failed} icon="bi-x-octagon" tone="danger" />
    <KpiCard label={t('Stuck in the queue')} value={counts.stuck} icon="bi-hourglass-split" tone="warning" />
    <KpiCard label={t('Succeeded')} value={counts.succeeded} icon="bi-check2-circle" tone="success" />
  </section>

  <div class="b2s-toolbar">
    <SearchField wrapperClass="b2s-toolbar__search" placeholder={t('Search a job, an error…')} ariaLabel={t('Filter jobs')} bind:value={query} />
    <select class="b2s-select" bind:value={statusFilter} aria-label={t('Status')}>
      <option value="all">{t('All statuses')}</option>
      <option value="active">{t('Running or queued')}</option>
      <option value="stuck">{t('Stuck in the queue')}</option>
      <option value="FAILED">{t('Failed')}</option>
      <option value="SUCCEEDED">{t('Succeeded')}</option>
      <option value="CANCELLED">{t('Cancelled')}</option>
    </select>
    <select class="b2s-select" bind:value={typeFilter} aria-label={t('Task')}>
      <option value="all">{t('All tasks')}</option>
      {#each typesPresent as type (type)}<option value={type}>{jobTypeLabel(type)}</option>{/each}
    </select>
    <button type="button" class="b2s-btn b2s-btn-secondary b2s-toolbar__end" on:click={exportJobs} disabled={filtered.length === 0}>
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
      <LoadingState />
    {:else if filtered.length === 0}
      <EmptyStateInline message={t('No job found.')} />
    {:else}
      <div class="b2s-table-wrap">
        <table class="b2s-table">
          <thead>
            <tr>
              <th>{t('Status')}</th>
              <th>{t('Task')}</th>
              <th>{t('Concerns')}</th>
              <th>{t('Updated')}</th>
              <th>{t('Error')}</th>
              <th class="obs-actions-col"><span class="visually-hidden">{t('Actions')}</span></th>
            </tr>
          </thead>
          <tbody>
            {#each pageRows as job (job.id)}
              {@const link = objectLink(job)}
              <tr>
                <td>
                  <StatusBadge compact label={isStuck(job) ? t('Stuck') : jobStatusLabel(job.status)} variant={isStuck(job) ? 'warning' : jobStatusVariant(job.status)} />
                </td>
                <td class="obs-main">
                  <strong>{jobTypeLabel(job.job_type, job.action)}</strong>
                  <small class="mono">#{job.id} · {job.job_type}</small>
                </td>
                <td>{#if link}<a href={link.href}>{link.label}</a>{:else}—{/if}</td>
                <td class="obs-date" title={formatDateTime(job.updated_at ?? job.created_at)}>{timeAgo(job.updated_at ?? job.created_at)}</td>
                <td class="obs-error">
                  {#if job.error_message || job.error_code}
                    <span title={String(job.error_code ?? '')}>{job.error_message ?? job.error_code}</span>
                  {:else}—{/if}
                </td>
                <td class="obs-actions">
                  {#if isActiveJob(job.status)}
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

<ConfirmActionModal
  open={!!cancelling}
  title={t('Stop the job')}
  subtitle={t('Job #{id} is cancelled; the worker skips it if it has not started yet.', { id: cancelling?.id ?? '' })}
  confirmLabel={t('Stop')}
  onConfirm={confirmCancel}
  onClose={() => (cancelling = null)}
/>

<style>
  .obs-jobs {
    display: grid;
    gap: 16px;
  }

  .obs-card {
    overflow: hidden;
  }

  .obs-main strong {
    display: block;
    font-weight: 600;
  }

  .obs-main small {
    display: block;
    margin-top: 2px;
    color: var(--b2s-color-text-muted);
  }

  .mono {
    font-family: var(--b2s-font-mono);
    font-size: var(--b2s-fs-xs);
  }

  .obs-date {
    white-space: nowrap;
  }

  .obs-error {
    max-width: 420px;
    color: var(--b2s-color-danger-strong);
    font-size: var(--b2s-fs-sm);
  }

  .obs-actions {
    white-space: nowrap;
    text-align: right;
  }

  .obs-actions-col {
    width: 1%;
  }
</style>
