<script lang="ts">
  import { onDestroy } from 'svelte';
  import { cancelAdminJob, listAdminJobs, type AdminProvisioningJob } from '$lib/api/admin-jobs';
  import { toast } from '$lib/utils/toast';
  import { toAppError } from '$lib/core/errors';

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

  const toDate = (value: unknown): Date | null => {
    const raw = String(value ?? '').trim();
    if (!raw) return null;
    const parsed = new Date(raw);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  };

  const formatDate = (value: unknown): string => {
    const parsed = toDate(value);
    if (!parsed) return '—';
    return parsed.toLocaleString('fr-FR', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    });
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
        toast.error(appError.message || 'Unable to load jobs');
      }
    } finally {
      if (!silent) isLoading = false;
    }
  };

  const cancelJob = async (job: AdminProvisioningJob) => {
    const jobId = Number(job?.id ?? 0);
    if (!Number.isFinite(jobId) || jobId <= 0) {
      toast.warning('Identifiant de job invalide');
      return;
    }
    if (!canCancel(job)) {
      toast.warning('This job is already terminal');
      return;
    }

    isCancelling = true;
    try {
      await cancelAdminJob(fetch, jobId, {
        reason: 'Cancelled by operator from observability/jobs',
        source: 'ui'
      });
      toast.success(`Job #${jobId} canceled`);
      await refreshJobs(true);
    } catch (error: unknown) {
      const appError = toAppError(error, { source: 'ui' });
      toast.error(appError.message || `Unable to cancel job #${jobId}`);
    } finally {
      isCancelling = false;
    }
  };

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
</script>

<div class="container-fluid jobs-page">
  <div class="jobs-head">
    <div>
      <h1 class="jobs-title">Jobs</h1>
      <div class="jobs-subtitle">Monitoring provisioning jobs and operator cancellations</div>
    </div>
    <div class="jobs-updated">Updated {formatDate(updatedAt)}</div>
  </div>

  <div class="card b2s-card jobs-summary">
    <div class="card-body d-flex flex-wrap align-items-center gap-3">
      <span class="summary-pill summary-pill--running">Active: {activeCount}</span>
      <span class="summary-pill summary-pill--neutral">Total: {jobs.length}</span>
      <span class="summary-pill summary-pill--error">Terminaux: {terminalCount}</span>
    </div>
  </div>

  <div class="card b2s-card jobs-toolbar">
    <div class="card-body d-flex flex-wrap align-items-center justify-content-between gap-2">
      <div class="d-flex align-items-center gap-2 flex-wrap">
        <input
          class="form-control form-control-sm"
          style="min-width: 280px"
          placeholder="Filtrer par id/correlation/type/action/erreur"
          bind:value={query}
        />
        <select class="form-select form-select-sm" style="width: 190px" bind:value={statusFilter}>
          <option value="all">All statuses</option>
          <option value="QUEUED">QUEUED</option>
          <option value="RUNNING">RUNNING</option>
          <option value="RETRYING">RETRYING</option>
          <option value="SUCCEEDED">SUCCEEDED</option>
          <option value="FAILED">FAILED</option>
          <option value="CANCELLED">CANCELLED</option>
        </select>
      </div>

      <button class="btn btn-sm btn-outline-primary" on:click={() => refreshJobs(false)} disabled={isLoading || isCancelling}>
        Refresh
      </button>
    </div>
  </div>

  {#if loadError}
    <div class="alert alert-danger mb-0">{loadError}</div>
  {/if}

  <div class="card b2s-card jobs-table-card">
    <div class="card-body p-0">
      <div class="table-responsive">
        <table class="table jobs-table mb-0 align-middle">
          <thead>
            <tr>
              <th>ID</th>
              <th>Statut</th>
              <th>Type</th>
              <th>Action</th>
              <th>Queue age (s)</th>
              <th>Republish</th>
              <th>Updated</th>
              <th>Error</th>
              <th class="text-end">Control</th>
            </tr>
          </thead>
          <tbody>
            {#if filtered.length === 0}
              <tr>
                <td colspan={9} class="jobs-empty">No job found.</td>
              </tr>
            {:else}
              {#each filtered as job (job.id)}
                <tr>
                  <td class="mono">#{job.id}</td>
                  <td>
                    <span class={`status-badge status-badge--${statusTone(normalizeStatus(job.status))}`}>
                      {normalizeStatus(job.status)}
                    </span>
                  </td>
                  <td class="mono">{String(job.job_type ?? '—')}</td>
                  <td>{String(job.action ?? '—')}</td>
                  <td class="mono">{job.queue_age_seconds ?? '—'}</td>
                  <td class="mono">{job.watchdog_republish_count ?? 0}</td>
                  <td class="mono">{formatDate(job.updated_at ?? job.created_at)}</td>
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
                    <button
                      class="btn btn-sm btn-outline-danger"
                      disabled={!canCancel(job) || isCancelling}
                      on:click={() => cancelJob(job)}
                    >
                      Kill
                    </button>
                  </td>
                </tr>
              {/each}
            {/if}
          </tbody>
        </table>
      </div>
    </div>
  </div>
</div>

<style>
  .jobs-page {
    display: grid;
    gap: 12px;
  }

  .jobs-head {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 12px;
  }

  .jobs-title {
    margin: 0;
    font-size: 1.5rem;
    font-weight: 700;
    color: #0f172a;
  }

  .jobs-subtitle,
  .jobs-updated {
    color: #64748b;
    font-size: 0.88rem;
  }

  .summary-pill {
    padding: 4px 10px;
    border-radius: 999px;
    font-size: 0.8rem;
    font-weight: 600;
    border: 1px solid transparent;
  }

  .summary-pill--running {
    background: #dbeafe;
    color: #1d4ed8;
    border-color: #bfdbfe;
  }

  .summary-pill--neutral {
    background: #f1f5f9;
    color: #334155;
    border-color: #e2e8f0;
  }

  .summary-pill--error {
    background: #fee2e2;
    color: #b91c1c;
    border-color: #fecaca;
  }

  .jobs-table thead th {
    background: #f8fafc;
    color: #334155;
    font-size: 0.82rem;
    white-space: nowrap;
  }

  .jobs-table tbody td {
    font-size: 0.84rem;
    color: #0f172a;
    vertical-align: middle;
  }

  .jobs-empty {
    text-align: center;
    color: #64748b;
    padding: 22px;
  }

  .mono {
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
    font-size: 0.78rem;
  }

  .status-badge {
    display: inline-block;
    border-radius: 999px;
    padding: 2px 8px;
    font-size: 0.74rem;
    font-weight: 700;
    border: 1px solid transparent;
  }

  .status-badge--running {
    background: #dbeafe;
    color: #1e40af;
    border-color: #bfdbfe;
  }

  .status-badge--success {
    background: #dcfce7;
    color: #166534;
    border-color: #bbf7d0;
  }

  .status-badge--error {
    background: #fee2e2;
    color: #b91c1c;
    border-color: #fecaca;
  }

  .status-badge--neutral {
    background: #f1f5f9;
    color: #334155;
    border-color: #e2e8f0;
  }

  .error-block {
    display: grid;
    gap: 2px;
  }
</style>

