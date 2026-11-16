<script lang="ts">
  import { t } from '$lib/i18n';
  import { live, type LiveTask } from '$lib/stores/live';
  import { tasksPanelOpen } from '$lib/stores/tasks-panel';
  import { listAdminJobs, type AdminProvisioningJob } from '$lib/api/admin-jobs';
  import { formatDateTime, timeAgo } from '$lib/utils/format';
  import { formatSeconds, isActiveJob, jobOriginLabel, jobStatusLabel, jobTypeLabel, normalizeJobStatus } from '$lib/utils/jobs';

  /**
   * Recent tasks, at the bottom of every page (administrators): one line folded (in progress, failures of the day),
   * the last tasks unfolded — what runs now (pushed live) then what ended lately. The health checks are left out.
   */
  let recent = $state<AdminProvisioningJob[]>([]);

  async function load() {
    try {
      recent = await listAdminJobs(fetch, { limit: 15, exclude_job_type: 'INFRA_HEALTH' });
    } catch {
      /* the line keeps what it knew */
    }
  }
  // Every minute folded, every 15 s unfolded (and at once when it unfolds)
  $effect(() => {
    const open = $tasksPanelOpen;
    void load();
    const timer = setInterval(() => void load(), open ? 15000 : 60000);
    return () => clearInterval(timer);
  });

  let running = $derived($live.tasks ?? []);
  let since = $derived(Date.now() - 24 * 3600 * 1000);
  let failures = $derived(recent.filter((job) => normalizeJobStatus(job.status) === 'FAILED' && Date.parse(String(job.finished_at ?? job.updated_at ?? '')) >= since).length);
  let finished = $derived(recent.filter((job) => !isActiveJob(job.status)).slice(0, 12));

  const percent = (task: LiveTask): number | null => {
    const p = task.progress as { chunks_done?: number; chunks_total?: number } | null;
    return p?.chunks_total ? Math.min(100, Math.round((100 * Number(p.chunks_done ?? 0)) / Number(p.chunks_total))) : null;
  };
  const tone = (status: unknown) => {
    const s = normalizeJobStatus(status);
    return s === 'FAILED' ? 'bad' : s === 'SUCCEEDED' ? 'ok' : isActiveJob(s) ? 'run' : 'mut';
  };
</script>

<section class="rt" class:is-open={$tasksPanelOpen} aria-label={t('Recent tasks')}>
  <button type="button" class="rt__bar" aria-expanded={$tasksPanelOpen} onclick={() => tasksPanelOpen.update((value) => !value)}>
    <b>{t('Recent tasks')}</b>
    {#if running.length}<span class="rt__pill is-run"><i aria-hidden="true"></i>{t('{count} in progress', { count: running.length })}</span>{/if}
    {#if failures}<span class="rt__pill is-bad"><i aria-hidden="true"></i>{t('{count} failure(s) in 24 h', { count: failures })}</span>{/if}
    {#if !running.length && !failures}<span class="rt__calm">{t('Nothing running')}</span>{/if}
    <span class="rt__toggle">{$tasksPanelOpen ? t('Fold') : t('Unfold')} <i class={`bi ${$tasksPanelOpen ? 'bi-chevron-down' : 'bi-chevron-up'}`} aria-hidden="true"></i></span>
  </button>
  {#if $tasksPanelOpen}
    <div class="rt__body">
      <div class="rt__row is-head"><span>{t('Task')}</span><span>{t('Target')}</span><span>{t('State')}</span><span>{t('Started by')}</span><span>{t('Start')}</span><span>{t('Duration')}</span></div>
      {#each running as task (task.id)}
        {@const pct = percent(task)}
        <div class="rt__row">
          <span>{jobTypeLabel(task.job_type, task.action)}</span>
          <span class="rt__target">{#if task.target?.href}<a href={task.target.href}>{task.target.label}</a>{:else}{task.target?.label ?? '—'}{/if}</span>
          <span class="rt__state is-run">{#if pct != null}<span class="rt__track"><span style={`width:${pct}%`}></span></span>{pct} %{:else}{task.status === 'QUEUED' ? t('waiting') : t('in progress')}{/if}</span>
          <span>—</span>
          <span>—</span>
          <span>{task.run_seconds != null ? formatSeconds(task.run_seconds) : '—'}</span>
        </div>
      {/each}
      {#each finished as job (job.id)}
        <div class="rt__row">
          <span>{jobTypeLabel(job.job_type, job.action)}</span>
          <span class="rt__target">{#if job.target?.href}<a href={job.target.href}>{job.target.label}</a>{:else}{job.target?.label ?? '—'}{/if}</span>
          <span class={`rt__state is-${tone(job.status)}`} title={job.error_message ?? ''}>{jobStatusLabel(job.status)}</span>
          <span>{job.requested_by ?? jobOriginLabel(job.origin)}</span>
          <span title={job.created_at ? formatDateTime(job.created_at) : ''}>{job.created_at ? timeAgo(job.created_at) : '—'}</span>
          <span>{job.run_seconds != null ? formatSeconds(job.run_seconds) : '—'}</span>
        </div>
      {:else}
        {#if !running.length}<p class="rt__empty">{t('No task lately.')}</p>{/if}
      {/each}
      <a class="rt__all" href="/observability?tab=jobs">{t('All the history')} →</a>
    </div>
  {/if}
</section>

<style>
  .rt { position: sticky; bottom: 0; z-index: 45; border-top: 1px solid var(--b2s-color-border); background: #fff; }
  .rt__bar { width: 100%; display: flex; align-items: center; gap: 14px; height: 34px; padding: 0 16px; border: 0; background: #fbfbfc; font: inherit; font-size: 13px; color: var(--b2s-color-text); text-align: left; cursor: pointer; }
  .rt__bar b { font-weight: 600; }
  .rt__pill { display: inline-flex; align-items: center; gap: 6px; }
  .rt__pill i { width: 8px; height: 8px; border-radius: 50%; }
  .rt__pill.is-run { color: #1d4ed8; }
  .rt__pill.is-run i { background: #60a5fa; }
  .rt__pill.is-bad { color: #a32626; }
  .rt__pill.is-bad i { background: #c23a3a; }
  .rt__calm { color: var(--b2s-color-text-muted); }
  .rt__toggle { margin-left: auto; color: var(--b2s-color-text-muted); }
  .rt__body { max-height: 260px; overflow: auto; border-top: 1px solid var(--b2s-color-border-soft); padding-bottom: 6px; }
  .rt__row { display: grid; grid-template-columns: minmax(180px, 1.3fr) minmax(180px, 1.4fr) 150px 150px 120px 90px; gap: 10px; align-items: center; min-height: 32px;
    padding: 0 16px; border-bottom: 1px solid #f4f5f7; font-size: 13px; }
  .rt__row > span { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .rt__row.is-head { min-height: 30px; color: var(--b2s-color-text-muted); font-size: 12px; font-weight: 500; }
  .rt__target { font-family: var(--b2s-font-mono, monospace); font-size: 12px; color: var(--b2s-color-text-soft); }
  .rt__state { display: flex; align-items: center; gap: 8px; font-size: 12px; font-weight: 600; }
  .rt__state.is-run { color: #1d4ed8; }
  .rt__state.is-ok { color: #0b7a4b; }
  .rt__state.is-bad { color: #a32626; }
  .rt__state.is-mut { color: var(--b2s-color-text-muted); }
  .rt__track { width: 60px; height: 5px; border-radius: 999px; background: #eef0f4; overflow: hidden; }
  .rt__track > span { display: block; height: 100%; background: #3b82f6; }
  .rt__empty { margin: 10px 16px; color: var(--b2s-color-text-muted); font-size: 13px; }
  .rt__all { display: inline-block; margin: 8px 16px 0; font-size: 13px; }
</style>
