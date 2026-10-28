<script lang="ts">
  import { t } from '$lib/i18n';
  import { formatDateTime, timeAgo, timeUntil } from '$lib/utils/format';
  import StatusBadge from '$lib/components/ui/StatusBadge.svelte';
  import { toast } from '$lib/stores/toast';
  import { reportUiError } from '$lib/errors';
  import { HEALTH_INTERVALS, SYNC_INTERVALS, intervalLabel } from '$lib/utils/infrastructure';
  import { runSchedule, updateSchedule, type InfraSchedule, type ScheduleTask } from '$lib/api/infrastructure';

  export let schedules: InfraSchedule[] = [];
  export let onChanged: () => Promise<void> | void = () => {};

  let busy: ScheduleTask | null = null;
  let running: ScheduleTask | null = null;

  const TASKS: Record<ScheduleTask, { icon: string; title: () => string; text: () => string; intervals: number[] }> = {
    health_check: {
      icon: 'bi-heart-pulse',
      title: () => t('Health check'),
      text: () => t('Checks the databases, the job queue and the workers, then every service, directory and file server from a worker.'),
      intervals: HEALTH_INTERVALS
    },
    data_sync: {
      icon: 'bi-arrow-repeat',
      title: () => t('Data sync'),
      text: () => t('Brings BornToShare in line with the directories and the file servers. Run by the workers.'),
      intervals: SYNC_INTERVALS
    }
  };

  const SYNC_PARTS: { key: 'snapshots' | 'shares' | 'acl_drift'; icon: string; title: () => string; text: () => string }[] = [
    { key: 'snapshots', icon: 'bi-cloud-arrow-down', title: () => t('Directory snapshots'), text: () => t('Users, groups and memberships of every source with “Snapshot inventory”.') },
    { key: 'shares', icon: 'bi-folder-symlink', title: () => t('Share discovery'), text: () => t('Shares of every file server: storage roots found or unreachable.') },
    { key: 'acl_drift', icon: 'bi-shield-exclamation', title: () => t('ACL and group drift'), text: () => t('ACL scan of every governed root, AD group members compared with the granted accesses. Differences raise alerts.') }
  ];

  const STATUS_VARIANT: Record<string, 'success' | 'warning' | 'error' | 'info' | 'muted'> = {
    success: 'success',
    partial: 'warning',
    failed: 'error',
    running: 'info'
  };

  function statusText(status: string | null): string {
    if (status === 'success') return t('Success');
    if (status === 'partial') return t('Partial');
    if (status === 'failed') return t('Failed');
    if (status === 'running') return t('Running');
    return t('Never run');
  }

  async function save(task: ScheduleTask, body: Parameters<typeof updateSchedule>[2]) {
    busy = task;
    try {
      const updated = await updateSchedule(fetch, task, body);
      schedules = schedules.map((s) => (s.task === task ? updated : s));
      toast.success(t('Schedule saved.'));
    } catch (e) {
      reportUiError(e, t('Unable to save the schedule.'), 'infrastructure.schedules.save');
    } finally {
      busy = null;
    }
  }

  async function runNow(task: ScheduleTask) {
    running = task;
    try {
      const result = await runSchedule(fetch, task);
      if (result.status === 'failed') toast.error(result.message);
      else if (result.status === 'partial') toast.warning(result.message);
      else toast.success(result.message);
      await onChanged();
    } catch (e) {
      reportUiError(e, t('Unable to run the task.'), 'infrastructure.schedules.run');
    } finally {
      running = null;
    }
  }

  function toggleOption(schedule: InfraSchedule, key: 'snapshots' | 'shares' | 'acl_drift', value: boolean) {
    void save(schedule.task, { options: { ...schedule.options, [key]: value } });
  }

  function summaryLines(schedule: InfraSchedule): string[] {
    const s = schedule.last_summary as Record<string, any>;
    if (!s || schedule.task !== 'data_sync') return [];
    const out: string[] = [];
    if (s.snapshots) out.push(t('Snapshots: {n} started, {r} already running', { n: s.snapshots.started ?? 0, r: s.snapshots.already_running ?? 0 }));
    if (s.shares) out.push(t('Share discovery: {n} file servers, {s} without account', { n: s.shares.started ?? 0, s: s.shares.skipped_without_account ?? 0 }));
    if (s.acl_drift) out.push(t('ACL scans: {n} of {r} governed roots', { n: s.acl_drift.acl_scans_started ?? 0, r: s.acl_drift.roots ?? 0 }));
    return out;
  }
</script>

<div class="sched">
  {#each [...schedules].sort((a, b) => (a.task === 'health_check' ? -1 : b.task === 'health_check' ? 1 : 0)) as schedule (schedule.task)}
    {@const meta = TASKS[schedule.task]}
    <section class="card" class:is-off={!schedule.is_enabled}>
      <header class="card__head">
        <span class="card__icon"><i class={`bi ${meta.icon}`} aria-hidden="true"></i></span>
        <div class="card__title">
          <h3>{meta.title()}</h3>
          <p>{meta.text()}</p>
        </div>
        <label class="switch">
          <input
            type="checkbox"
            class="cap-switch"
            checked={schedule.is_enabled}
            disabled={busy === schedule.task}
            on:change={(e) => save(schedule.task, { is_enabled: e.currentTarget.checked })}
          />
          <span>{schedule.is_enabled ? t('Enabled') : t('Disabled')}</span>
        </label>
      </header>

      <div class="card__body">
        <label class="interval">
          <span>{t('Frequency')}</span>
          <select
            class="b2s-select"
            value={schedule.interval_minutes}
            disabled={busy === schedule.task}
            on:change={(e) => save(schedule.task, { interval_minutes: Number(e.currentTarget.value) })}
          >
            {#each meta.intervals.includes(schedule.interval_minutes) ? meta.intervals : [...meta.intervals, schedule.interval_minutes].sort((a, b) => a - b) as minutes (minutes)}
              <option value={minutes}>{intervalLabel(minutes)}</option>
            {/each}
          </select>
        </label>

        <dl class="timeline">
          <div>
            <dt>{t('Last run')}</dt>
            <dd>
              {#if schedule.last_run_at}
                <span title={formatDateTime(schedule.last_run_at)}>{timeAgo(schedule.last_run_at)}</span>
              {:else}—{/if}
              <StatusBadge compact={true} status={schedule.last_status ?? 'never'} label={statusText(schedule.last_status)} variant={STATUS_VARIANT[schedule.last_status ?? ''] ?? 'muted'} />
            </dd>
          </div>
          <div>
            <dt>{t('Next run')}</dt>
            <dd>
              {#if !schedule.is_enabled}{t('Paused')}
              {:else if schedule.next_run_at}<span title={formatDateTime(schedule.next_run_at)}>{timeUntil(schedule.next_run_at)}</span>
              {:else}{t('At the next scheduler pass')}{/if}
            </dd>
          </div>
        </dl>

        {#if schedule.last_message}
          <p class="last-msg">{t(schedule.last_message)}</p>
        {/if}
        {#each summaryLines(schedule) as line (line)}
          <p class="last-line"><i class="bi bi-dot" aria-hidden="true"></i>{line}</p>
        {/each}

        {#if schedule.task === 'data_sync'}
          <div class="parts">
            {#each SYNC_PARTS as part (part.key)}
              <label class="part" class:is-on={schedule.options?.[part.key] !== false}>
                <span class="part__icon"><i class={`bi ${part.icon}`} aria-hidden="true"></i></span>
                <span class="part__copy">
                  <strong>{part.title()}</strong>
                  <small>{part.text()}</small>
                </span>
                <input
                  type="checkbox"
                  class="cap-switch"
                  checked={schedule.options?.[part.key] !== false}
                  disabled={busy === schedule.task}
                  on:change={(e) => toggleOption(schedule, part.key, e.currentTarget.checked)}
                />
              </label>
            {/each}
          </div>
        {/if}
      </div>

      <footer class="card__foot">
        <button type="button" class="b2s-btn b2s-btn-secondary" on:click={() => runNow(schedule.task)} disabled={running !== null || schedule.last_status === 'running'}>
          <i class={`bi ${running === schedule.task ? 'bi-hourglass-split' : 'bi-play-fill'}`} aria-hidden="true"></i>
          {running === schedule.task ? t('Running…') : t('Run now')}
        </button>
      </footer>
    </section>
  {/each}
</div>

<style>
  .sched {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 14px;
    align-items: start;
  }

  .card {
    border: 1px solid #e2e8f0;
    border-radius: var(--b2s-radius-md);
    background: #ffffff;
    display: grid;
  }

  .card.is-off .card__body {
    opacity: 0.6;
  }

  .card__head {
    display: grid;
    grid-template-columns: auto 1fr auto;
    gap: 12px;
    align-items: start;
    padding: 16px 18px;
    border-bottom: 1px solid #f1f5f9;
  }

  .card__icon {
    width: 38px;
    height: 38px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: var(--b2s-radius-sm);
    background: #eef2ff;
    color: #1e3a8a;
    font-size: 1.15rem;
  }

  .card__title h3 {
    margin: 0;
    font-size: var(--b2s-fs-md);
    color: #071638;
  }

  .card__title p {
    margin: 3px 0 0;
    font-size: var(--b2s-fs-xs);
    color: #64748b;
    line-height: 1.4;
  }

  .switch {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-size: var(--b2s-fs-xs);
    color: #334155;
    cursor: pointer;
    white-space: nowrap;
  }

  .card__body {
    display: grid;
    gap: 12px;
    padding: 14px 18px;
  }

  .interval {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 10px;
    align-items: center;
    font-size: var(--b2s-fs-sm);
    color: #334155;
  }

  .interval select {
    max-width: 240px;
  }

  .timeline {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
    margin: 0;
  }

  .timeline div {
    padding: 10px 12px;
    border-radius: var(--b2s-radius-sm);
    background: #f8fafc;
  }

  .timeline dt {
    font-size: var(--b2s-fs-xs);
    color: #64748b;
  }

  .timeline dd {
    margin: 4px 0 0;
    display: flex;
    gap: 8px;
    align-items: center;
    flex-wrap: wrap;
    font-size: var(--b2s-fs-sm);
    color: #0f172a;
    font-weight: 600;
  }

  .last-msg,
  .last-line {
    margin: 0;
    font-size: var(--b2s-fs-xs);
    color: #475569;
  }

  .parts {
    display: grid;
    gap: 8px;
  }

  .part {
    display: grid;
    grid-template-columns: auto 1fr auto;
    gap: 10px;
    align-items: center;
    padding: 10px 12px;
    border: 1px solid #e2e8f0;
    border-radius: var(--b2s-radius-sm);
    cursor: pointer;
  }

  .part.is-on {
    border-color: #c7d2fe;
    background: #f8faff;
  }

  .part__icon {
    width: 28px;
    height: 28px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: var(--b2s-radius-sm);
    background: #eff6ff;
    color: #0b63f4;
  }

  .part__copy strong,
  .part__copy small {
    display: block;
  }

  .part__copy strong {
    font-size: var(--b2s-fs-xs);
    color: #071638;
  }

  .part__copy small {
    font-size: var(--b2s-fs-xs);
    color: #64748b;
    margin-top: 2px;
  }

  .card__foot {
    display: flex;
    justify-content: flex-end;
    padding: 12px 18px;
    border-top: 1px solid #f1f5f9;
  }

  .cap-switch {
    appearance: none;
    flex: none;
    width: 34px;
    height: 19px;
    border-radius: var(--b2s-radius-pill);
    background: #cbd5e1;
    position: relative;
    cursor: pointer;
    transition: background 0.16s ease;
  }

  .cap-switch::after {
    content: "";
    position: absolute;
    top: 3px;
    left: 3px;
    width: 13px;
    height: 13px;
    border-radius: 50%;
    background: #ffffff;
    transition: transform 0.16s ease;
  }

  .cap-switch:checked {
    background: var(--b2s-topbar-bg, #0b1530);
  }

  .cap-switch:checked::after {
    transform: translateX(15px);
  }

  @media (max-width: 1100px) {
    .sched {
      grid-template-columns: 1fr;
    }
  }
</style>
