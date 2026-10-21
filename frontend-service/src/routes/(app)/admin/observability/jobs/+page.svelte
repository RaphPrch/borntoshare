<script lang="ts">
  import { csvFilename, downloadCsv } from '$lib/utils/csv';
  import SearchField from '$lib/components/ui/SearchField.svelte';
  import StatusBadge from '$lib/components/ui/StatusBadge.svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import PageHeader from '$lib/components/ui/PageHeader.svelte';
  import Pagination from '$lib/components/ui/Pagination.svelte';
  import { t } from '$lib/i18n';
  import { formatDateTime } from '$lib/utils/format';
  import { onDestroy } from 'svelte';
  import { cancelAdminJob, listAdminJobs, type AdminProvisioningJob } from '$lib/api/admin-jobs';
  import { toast } from '$lib/stores/toast';
  import { toAppError } from '$lib/errors';

  export let data: {
    initialJobs?: AdminProvisioningJob[];
    generatedAt?: string;
  };

  const POLL_INTERVAL_MS = 5000;

  let query = '';
  let statusFilter = 'all';
  let isLoading = false;
  let isCancelling = false;
  let loadError: string | null = null;
  let jobs: AdminProvisioningJob[] = Array.isArray(data?.initialJobs) ? data.initialJobs : [];
  let updatedAt = String(data?.generatedAt ?? new Date().toISOString());
  let pollTimer: ReturnType<typeof setInterval> | null = null;
  let page = 1;
  let pageSize = 25;

  const toDate = (value: unknown): Date | null => {
    const raw = String(value ?? '').trim();
    if (!raw) return null;
    const parsed = new Date(raw);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  };

  const normalizeStatus = (raw: unknown): string => {
    const s = String(raw ?? '').trim().toUpperCase();
    if (!s) return 'UNKNOWN';
    if (s === 'CANCELED') return 'CANCELLED';
    return s;
  };

  const isTerminal = (status: string): boolean =>
    ['SUCCEEDED', 'FAILED', 'CANCELLED'].includes(normalizeStatus(status));

  const canCancel = (job: AdminProvisioningJob): boolean => {
    const status = normalizeStatus(job?.status);
    return !isTerminal(status) && status !== 'UNKNOWN';
  };

  const JOB_STATUS_VARIANTS = { running: 'info', success: 'success', error: 'error', neutral: 'muted' } as const;

  const statusTone = (status: string): 'running' | 'success' | 'error' | 'neutral' => {
    const s = normalizeStatus(status);
    if (['CREATED', 'QUEUED', 'RUNNING', 'RETRYING'].includes(s)) return 'running';
    if (s === 'SUCCEEDED') return 'success';
    if (['FAILED', 'CANCELLED'].includes(s)) return 'error';
    return 'neutral';
  };

  const toSearchText = (job: AdminProvisioningJob): string => {
    return [
      job?.id,
      job?.correlation_id,
      job?.job_type,
      job?.action,
      job?.status,
      job?.error_code,
      job?.error_message
    ]
      .map((v) => String(v ?? '').toLowerCase())
      .join(' ');
  };

  const refreshJobs = async (silent = false) => {
    if (!silent) {
      isLoading = true;
      loadError = null;
    }
    try {
      const rows = await listAdminJobs(fetch, { limit: 200 });
      jobs = Array.isArray(rows) ? rows : [];
      updatedAt = new Date().toISOString();
    } catch (error: unknown) {
      const appError = toAppError(error, { source: 'ui' });
      loadError = appError.message;
      if (!silent) {
        toast.error(appError.message || t('Unable to load jobs'));
      }
    } finally {
      if (!silent) isLoading = false;
    }
  };

  const cancelJob = async (job: AdminProvisioningJob) => {
    const jobId = Number(job?.id ?? 0);
    if (!Number.isFinite(jobId) || jobId <= 0) {
      toast.warning(t('Identifiant de job invalide'));
      return;
    }
    if (!canCancel(job)) {
      toast.warning(t('This job is already terminal'));
      return;
    }

    isCancelling = true;
    try {
      await cancelAdminJob(fetch, jobId, {
        reason: 'Cancelled by operator from observability/jobs',
        source: 'ui'
      });
      toast.success(t('Job #{jobId} canceled', { jobId }));
      await refreshJobs(true);
    } catch (error: unknown) {
      const appError = toAppError(error, { source: 'ui' });
      toast.error(appError.message || t('Unable to cancel job #{jobId}', { jobId }));
    } finally {
      isCancelling = false;
    }
  };

  const exportJobs = () =>
    downloadCsv(csvFilename('jobs'), [
      { header: 'ID', value: (job: AdminProvisioningJob) => job.id },
      { header: t('Status'), value: (job: AdminProvisioningJob) => normalizeStatus(job.status) },
      { header: t('Type'), value: (job: AdminProvisioningJob) => job.job_type },
      { header: t('Action'), value: (job: AdminProvisioningJob) => job.action },
      { header: t('Updated'), value: (job: AdminProvisioningJob) => formatDateTime(job.updated_at ?? job.created_at) },
      { header: t('Error code'), value: (job: AdminProvisioningJob) => job.error_code },
      { header: t('Error'), value: (job: AdminProvisioningJob) => job.error_message },
      { header: t('Correlation ID'), value: (job: AdminProvisioningJob) => job.correlation_id }
    ], filtered);

  const startPolling = () => {
    if (pollTimer) return;
    pollTimer = setInterval(() => {
      void refreshJobs(true);
    }, POLL_INTERVAL_MS);
  };

  startPolling();

  onDestroy(() => {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  });

  $: activeCount = jobs.filter((j) => ['CREATED', 'QUEUED', 'RUNNING', 'RETRYING'].includes(normalizeStatus(j?.status))).length;
  $: terminalCount = jobs.filter((j) => isTerminal(normalizeStatus(j?.status))).length;
  $: q = query.trim().toLowerCase();
  $: filtered = jobs
    .filter((job) => {
      if (statusFilter === 'all') return true;
      return normalizeStatus(job?.status) === normalizeStatus(statusFilter);
    })
    .filter((job) => !q || toSearchText(job).includes(q))
    .sort((a, b) => {
      const da = toDate(a?.updated_at ?? a?.created_at)?.getTime() ?? 0;
      const db = toDate(b?.updated_at ?? b?.created_at)?.getTime() ?? 0;
      return db - da;
    });
  $: query, statusFilter, (page = 1);
  $: pageRows = filtered.slice((page - 1) * pageSize, page * pageSize);
</script>

<div class="jobs-page">
  <PageHeader title={t('Jobs')} subtitle={t('Monitoring provisioning jobs and operator cancellations')}>
    <svelte:fragment slot="actions">
      <span>{t('Updated {formatDateTime}', { formatDateTime: formatDateTime(updatedAt) })}</span>
    </svelte:fragment>
  </PageHeader>

  <div class="jobs-summary">
    <StatusBadge variant="info" label={t('Active: {activeCount}', { activeCount })} />
    <StatusBadge variant="muted" showDot={false} label={t('Total: {jobsCount}', { jobsCount: jobs.length })} />
    <StatusBadge variant="muted" showDot={false} label={t('Finished: {terminalCount}', { terminalCount })} />
  </div>

  <div class="b2s-toolbar">
        <SearchField
          wrapperClass="b2s-toolbar__search"
          placeholder={t('Filtrer par id/correlation/type/action/erreur')}
          ariaLabel={t('Filter jobs')}
          bind:value={query}
        />
        <select class="b2s-select" bind:value={statusFilter} aria-label={t('Status')}>
          <option value="all">{t('All statuses')}</option>
          <option value="QUEUED">QUEUED</option>
          <option value="RUNNING">RUNNING</option>
          <option value="RETRYING">RETRYING</option>
          <option value="SUCCEEDED">SUCCEEDED</option>
          <option value="FAILED">FAILED</option>
          <option value="CANCELLED">CANCELLED</option>
        </select>
<button type="button" class="b2s-btn b2s-btn-secondary b2s-toolbar__end" on:click={exportJobs} disabled={filtered.length === 0}>
          <i class="bi bi-download" aria-hidden="true"></i>
          {t('Export CSV')}
        </button>
        <button class="b2s-btn b2s-btn-secondary" on:click={() => refreshJobs(false)} disabled={isLoading || isCancelling}>
          <i class="bi bi-arrow-clockwise" aria-hidden="true"></i>
          {t('Refresh')}
        </button>
  </div>

  {#if loadError}
    <InlineAlert tone="error">{loadError}</InlineAlert>
  {/if}

  <div class="card b2s-card jobs-table-card">
    <div class="card-body p-0">
      <div class="table-responsive">
        <table class="b2s-table jobs-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>{t('Statut')}</th>
              <th>{t('Type')}</th>
              <th>{t('Action')}</th>
              <th>{t('Queue age (s)')}</th>
              <th>{t('Republish')}</th>
              <th>{t('Updated')}</th>
              <th>{t('Error')}</th>
              <th class="text-end">{t('Control')}</th>
            </tr>
          </thead>
          <tbody>
            {#if filtered.length === 0}
              <tr>
                <td colspan={9} class="jobs-empty">{t('No job found.')}</td>
              </tr>
            {:else}
              {#each pageRows as job (job.id)}
                <tr>
                  <td class="mono">#{job.id}</td>
                  <td>
                    <StatusBadge compact label={normalizeStatus(job.status)} variant={JOB_STATUS_VARIANTS[statusTone(job.status)]} />
                  </td>
                  <td class="mono">{String(job.job_type ?? '—')}</td>
                  <td>{String(job.action ?? '—')}</td>
                  <td class="num">{job.queue_age_seconds ?? '—'}</td>
                  <td class="num">{job.watchdog_republish_count ?? 0}</td>
                  <td class="num">{formatDateTime(job.updated_at ?? job.created_at)}</td>
                  <td>
                    {#if job.error_code || job.error_message}
                      <div class="error-block">
                        <div class="mono">{String(job.error_code ?? 'ERROR')}</div>
                        <div>{String(job.error_message ?? '')}</div>
                      </div>
                    {:else}
                      —
                    {/if}
                  </td>
                  <td class="text-end">
                    {#if canCancel(job)}
                      <button
                        class="b2s-btn b2s-btn-sm b2s-btn-danger-outline"
                        disabled={isCancelling}
                        on:click={() => cancelJob(job)}
                      >
                        {t('Kill')}
                      </button>
                    {/if}
                  </td>
                </tr>
              {/each}
            {/if}
          </tbody>
        </table>
      </div>
      {#if filtered.length > 0}
        <Pagination total={filtered.length} bind:page bind:pageSize />
      {/if}
    </div>
  </div>
</div>

<style>
  .jobs-summary {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .jobs-page {
    display: grid;
    gap: 16px;
    padding: var(--b2s-page-padding);
  }

  .jobs-table thead th {
    white-space: nowrap;
  }

  .jobs-empty {
    text-align: center;
    color: #64748b;
    padding: 22px;
  }

  .num {
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }

  .mono {
    font-family: var(--b2s-font-mono);
    font-size: var(--b2s-fs-xs);
  }

  .error-block {
    display: grid;
    gap: 2px;
  }
</style>

