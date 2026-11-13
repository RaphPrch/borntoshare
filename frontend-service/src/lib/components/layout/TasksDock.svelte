<script lang="ts">
  import { fly } from 'svelte/transition';
  import { t } from '$lib/i18n';
  import { live, type LiveTask } from '$lib/stores/live';
  import { dur, MOTION } from '$lib/utils/motion';
  import { formatSeconds, jobTypeLabel } from '$lib/utils/jobs';

  /**
   * Tasks in progress (administrators): measures, access being applied, directory reads… pushed live by /live.
   * Folded into a pill by default; a task that ends leaves the list on the next push.
   */
  let expanded = $state(false);
  let dismissedKey = $state('');

  let tasks = $derived($live.tasks);
  let key = $derived(tasks.map((task) => `${task.id}:${task.status}`).join(','));
  // Hidden by the person until the list changes
  let visible = $derived(tasks.length > 0 && key !== dismissedKey);
  const percent = (task: LiveTask): number | null => {
    const p = task.progress as { chunks_done?: number; chunks_total?: number } | null;
    return p?.chunks_total ? Math.min(100, Math.round((100 * Number(p.chunks_done ?? 0)) / Number(p.chunks_total))) : null;
  };
  const detail = (task: LiveTask): string => {
    if (task.stuck) return t('no news, maybe stuck');
    if (task.status === 'QUEUED') return t('waiting');
    const pct = percent(task);
    if (pct != null) return `${pct} %`;
    return task.run_seconds != null ? formatSeconds(task.run_seconds) : t('in progress');
  };
</script>

{#if visible}
  <aside class="td" class:is-open={expanded} aria-label={t('Tasks in progress')} transition:fly={{ y: 16, duration: dur(MOTION.base) }}>
    <header>
      <button type="button" class="td__head" aria-expanded={expanded} onclick={() => (expanded = !expanded)}>
        <span class="td__spin" aria-hidden="true"></span>
        <strong>{t('{count} task(s) in progress', { count: tasks.length })}</strong>
        <i class={`bi ${expanded ? 'bi-chevron-down' : 'bi-chevron-up'}`} aria-hidden="true"></i>
      </button>
      <a href="/observability?tab=jobs" class="td__all">{t('See all')}</a>
      <button type="button" class="td__close" aria-label={t('Hide')} onclick={() => (dismissedKey = key)}><i class="bi bi-x" aria-hidden="true"></i></button>
    </header>
    {#if expanded}
      <ul>
        {#each tasks as task (task.id)}
          {@const pct = percent(task)}
          <li class:is-stuck={Boolean(task.stuck)}>
            <div class="td__line">
              <span>{jobTypeLabel(task.job_type, task.action)}{#if task.target} · {#if task.target.href}<a href={task.target.href}>{task.target.label}</a>{:else}{task.target.label}{/if}{/if}</span>
              <small>{detail(task)}</small>
            </div>
            {#if task.status !== 'QUEUED'}
              <span class="td__bar" class:is-flow={pct == null}><span style={pct != null ? `width:${pct}%` : ''}></span></span>
            {/if}
          </li>
        {/each}
      </ul>
    {/if}
  </aside>
{/if}

<style>
  .td { position: fixed; left: 104px; bottom: 20px; z-index: 60; width: 360px; padding: 10px 12px; border: 1px solid var(--b2s-color-border-soft); border-radius: 14px;
    background: var(--b2s-color-surface); box-shadow: 0 14px 34px rgba(14, 18, 24, 0.14); }
  header { display: flex; align-items: center; gap: 8px; }
  .td__head { flex: 1; display: flex; align-items: center; gap: 10px; border: 0; background: none; padding: 2px 0; font: inherit; font-size: var(--b2s-fs-sm); color: var(--b2s-color-text); cursor: pointer; text-align: left; }
  .td__head i { margin-left: auto; color: var(--b2s-color-text-muted); }
  .td__all { font-size: var(--b2s-fs-xs); }
  .td__close { border: 0; background: none; color: var(--b2s-color-text-muted); cursor: pointer; padding: 2px 4px; font-size: 16px; }
  .td__spin { width: 14px; height: 14px; border-radius: 50%; border: 2px solid #d9f99d; border-top-color: #65a30d; animation: td-spin 0.9s linear infinite; }
  ul { list-style: none; margin: 10px 0 0; padding: 0; display: grid; gap: 10px; max-height: 320px; overflow: auto; }
  li { display: grid; gap: 5px; }
  .td__line { display: flex; justify-content: space-between; gap: 10px; font-size: var(--b2s-fs-sm); }
  .td__line span { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .td__line small { flex: none; color: var(--b2s-color-text-muted); }
  .is-stuck .td__line small { color: #b45309; }
  .td__bar { display: block; height: 6px; border-radius: 999px; background: #eef0ec; overflow: hidden; }
  .td__bar > span { display: block; height: 100%; border-radius: 999px; background: #84cc16; transition: width 400ms ease; }
  .td__bar.is-flow > span { width: 40%; background-image: repeating-linear-gradient(90deg, #a3e635 0 20px, #d9f99d 20px 40px); animation: td-flow 1.2s linear infinite; }
  @keyframes td-spin { to { transform: rotate(360deg); } }
  @keyframes td-flow { from { transform: translateX(-100%); } to { transform: translateX(250%); } }
  @media (prefers-reduced-motion: reduce) { .td__spin, .td__bar.is-flow > span { animation: none; } }
</style>
