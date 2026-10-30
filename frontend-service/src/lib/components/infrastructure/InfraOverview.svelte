<script lang="ts">
  import { t } from '$lib/i18n';
  import { timeAgo, timeUntil } from '$lib/utils/format';
  import StatusBadge from '$lib/components/ui/StatusBadge.svelte';
  import AvailabilityBar from './AvailabilityBar.svelte';
  import { STATUS_VARIANT, groupComponents, statusLabel, worstStatus } from '$lib/utils/infrastructure';
  import type { HealthStatus, InfraOverview } from '$lib/api/infrastructure';

  export let overview: InfraOverview;
  export let running = false;
  export let onRunHealthCheck: () => void;

  let filter: HealthStatus | 'all' = 'all';

  $: components = overview.components ?? [];
  $: overall = components.length ? worstStatus(components) : 'unknown';
  $: lastCheck = components.reduce<string | null>((latest, c) => (c.checked_at && (!latest || c.checked_at > latest) ? c.checked_at : latest), null);
  $: health = (overview.schedules ?? []).find((s) => s.task === 'health_check');
  $: visible = filter === 'all' ? components : components.filter((c) => c.status === filter);
  $: groups = groupComponents(visible);

  const HERO: Record<HealthStatus, { icon: string; title: () => string; text: () => string }> = {
    healthy: { icon: 'bi-check-circle-fill', title: () => t('All systems operational'), text: () => t('Every monitored component answers normally.') },
    degraded: { icon: 'bi-exclamation-circle-fill', title: () => t('Degraded performance'), text: () => t('Some components answer slowly or partially.') },
    down: { icon: 'bi-x-octagon-fill', title: () => t('Incident in progress'), text: () => t('At least one component does not answer.') },
    unknown: { icon: 'bi-question-circle-fill', title: () => t('State not known yet'), text: () => t('Run a health check, or add a worker so the checks can run.') }
  };

  const KPIS: { key: HealthStatus; label: () => string; icon: string }[] = [
    { key: 'healthy', label: () => t('Operational'), icon: 'bi-check-circle' },
    { key: 'degraded', label: () => t('Degraded'), icon: 'bi-exclamation-circle' },
    { key: 'down', label: () => t('Down'), icon: 'bi-x-octagon' },
    { key: 'unknown', label: () => t('Unknown'), icon: 'bi-question-circle' }
  ];

  function toggleFilter(key: HealthStatus) {
    filter = filter === key ? 'all' : key;
  }
</script>

<section class={`hero is-${overall}`}>
  <i class={`bi ${HERO[overall].icon} hero__icon`} aria-hidden="true"></i>
  <div class="hero__copy">
    <h2>{HERO[overall].title()}</h2>
    <p>
      {HERO[overall].text()}
      {#if lastCheck}· {t('Last check {ago}', { ago: timeAgo(lastCheck) })}{/if}
      {#if health?.is_enabled && health.next_run_at}· {t('next check {when}', { when: timeUntil(health.next_run_at) })}{/if}
    </p>
  </div>
  <button type="button" class="b2s-btn b2s-btn-primary hero__action" on:click={onRunHealthCheck} disabled={running}>
    <i class={`bi ${running ? 'bi-hourglass-split' : 'bi-activity'}`} aria-hidden="true"></i>
    {running ? t('Checking…') : t('Run a health check')}
  </button>
</section>

<div class="kpis">
  {#each KPIS as kpi (kpi.key)}
    <button
      type="button"
      class={`kpi is-${kpi.key}`}
      class:is-active={filter === kpi.key}
      aria-pressed={filter === kpi.key}
      on:click={() => toggleFilter(kpi.key)}
    >
      <i class={`bi ${kpi.icon}`} aria-hidden="true"></i>
      <span class="kpi__value">{overview.summary?.[kpi.key] ?? 0}</span>
      <span class="kpi__label">{kpi.label()}</span>
    </button>
  {/each}
</div>

{#if filter !== 'all'}
  <div class="filter-note">
    {t('Showing: {status}', { status: statusLabel(filter) })}
    <button type="button" class="b2s-btn b2s-btn-ghost b2s-btn-sm" on:click={() => (filter = 'all')}>{t('Show all')}</button>
  </div>
{/if}

{#if components.length === 0}
  <div class="empty">
    <i class="bi bi-broadcast" aria-hidden="true"></i>
    <strong>{t('No check yet')}</strong>
    <span>{t('The health check runs every few minutes. Run one now to fill this page.')}</span>
  </div>
{/if}

{#each groups as group (group.key)}
  <section class="group">
    <header class="group__head">
      <span class="group__icon"><i class={`bi ${group.icon}`} aria-hidden="true"></i></span>
      <h3>{group.label}</h3>
      <span class="group__count">{group.items.length}</span>
      <span class="group__status">
        <StatusBadge compact={true} status={worstStatus(group.items)} label={statusLabel(worstStatus(group.items))} variant={STATUS_VARIANT[worstStatus(group.items)]} />
      </span>
    </header>
    <ul class="rows">
      {#each group.items as item (item.component)}
        <li class="row">
          <span class={`row__dot is-${item.status}`} aria-hidden="true"></span>
          <div class="row__main">
            <strong>{item.label}</strong>
            <small title={item.message ?? ''}>
              {#if item.stale}{t('No recent result')} · {/if}{item.message ?? '—'}
            </small>
          </div>
          <div class="row__bar">
            <AvailabilityBar points={item.history} />
            <small>{item.uptime_24h !== null ? t('{pct}% over 24 h', { pct: item.uptime_24h }) : t('No history')}</small>
          </div>
          <div class="row__meta">
            <span class="row__latency">{item.latency_ms !== null ? `${item.latency_ms} ms` : '—'}</span>
            <small title={item.checked_by ?? ''}>{item.checked_at ? timeAgo(item.checked_at) : '—'}</small>
          </div>
        </li>
      {/each}
    </ul>
  </section>
{/each}

<style>
  .hero {
    display: grid;
    grid-template-columns: auto 1fr auto;
    gap: 16px;
    align-items: center;
    padding: 20px 22px;
    border-radius: var(--b2s-radius-md);
    border: 1px solid;
    margin-bottom: 14px;
  }

  .hero.is-healthy {
    background: linear-gradient(135deg, var(--b2s-color-success-soft), #ffffff 70%);
    border-color: var(--b2s-color-success-border);
  }

  .hero.is-degraded {
    background: linear-gradient(135deg, #fffbeb, #ffffff 70%);
    border-color: #fde68a;
  }

  .hero.is-down {
    background: linear-gradient(135deg, var(--b2s-color-danger-soft), #ffffff 70%);
    border-color: var(--b2s-color-danger-border);
  }

  .hero.is-unknown {
    background: linear-gradient(135deg, var(--b2s-color-surface-soft), #ffffff 70%);
    border-color: var(--b2s-color-border-soft);
  }

  .hero__icon {
    font-size: 2.1rem;
  }

  .is-healthy .hero__icon {
    color: var(--b2s-color-success);
  }

  .is-degraded .hero__icon {
    color: var(--b2s-color-warning);
  }

  .is-down .hero__icon {
    color: var(--b2s-color-danger);
  }

  .is-unknown .hero__icon {
    color: var(--b2s-color-text-faint);
  }

  .hero__copy h2 {
    margin: 0;
    font-size: var(--b2s-fs-xl);
    color: var(--b2s-color-heading);
  }

  .hero__copy p {
    margin: 4px 0 0;
    color: var(--b2s-color-text-soft);
    font-size: var(--b2s-fs-sm);
  }

  .kpis {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 10px;
    margin-bottom: 14px;
  }

  .kpi {
    display: grid;
    grid-template-columns: auto 1fr;
    grid-template-rows: auto auto;
    column-gap: 10px;
    align-items: center;
    padding: 12px 14px;
    border: 1px solid var(--b2s-color-border-soft);
    border-radius: var(--b2s-radius-sm);
    background: var(--b2s-color-surface);
    text-align: left;
    cursor: pointer;
    transition: border-color 0.15s ease, box-shadow 0.15s ease;
  }

  .kpi:hover,
  .kpi.is-active {
    border-color: var(--b2s-color-text-faint);
    box-shadow: 0 4px 14px rgba(15, 23, 42, 0.06);
  }

  .kpi i {
    grid-row: span 2;
    font-size: 1.3rem;
  }

  .kpi.is-healthy i {
    color: var(--b2s-color-success);
  }

  .kpi.is-degraded i {
    color: var(--b2s-color-warning);
  }

  .kpi.is-down i {
    color: var(--b2s-color-danger);
  }

  .kpi.is-unknown i {
    color: var(--b2s-color-text-faint);
  }

  .kpi__value {
    font-size: var(--b2s-fs-xl);
    font-weight: 700;
    color: var(--b2s-color-heading);
    line-height: 1.1;
  }

  .kpi__label {
    font-size: var(--b2s-fs-xs);
    color: var(--b2s-color-text-muted);
  }

  .filter-note {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 10px;
    font-size: var(--b2s-fs-sm);
    color: var(--b2s-color-text-soft);
  }

  .empty {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
    padding: 36px 16px;
    border: 1px dashed var(--b2s-color-border-mid);
    border-radius: var(--b2s-radius-md);
    color: var(--b2s-color-text-muted);
    text-align: center;
  }

  .empty i {
    font-size: 1.8rem;
    color: var(--b2s-color-text-faint);
  }

  .group {
    border: 1px solid var(--b2s-color-border-soft);
    border-radius: var(--b2s-radius-md);
    background: var(--b2s-color-surface);
    margin-bottom: 12px;
    overflow: hidden;
  }

  .group__head {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 12px 16px;
    background: var(--b2s-color-surface-soft);
    border-bottom: 1px solid var(--b2s-color-border-soft);
  }

  .group__icon {
    width: 28px;
    height: 28px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: var(--b2s-radius-sm);
    background: var(--b2s-color-primary-soft);
    color: #1e3a8a;
  }

  .group__head h3 {
    margin: 0;
    font-size: var(--b2s-fs-md);
    color: var(--b2s-color-heading);
  }

  .group__count {
    font-size: var(--b2s-fs-xs);
    color: var(--b2s-color-text-muted);
    background: var(--b2s-color-border-soft);
    border-radius: var(--b2s-radius-pill);
    padding: 1px 8px;
  }

  .group__status {
    margin-left: auto;
  }

  .rows {
    list-style: none;
    margin: 0;
    padding: 0;
  }

  .row {
    display: grid;
    grid-template-columns: auto minmax(0, 1.4fr) minmax(160px, 1fr) 90px;
    gap: 14px;
    align-items: center;
    padding: 10px 16px;
    border-top: 1px solid var(--b2s-color-neutral-soft);
  }

  .row:first-child {
    border-top: 0;
  }

  .row__dot {
    display: block;
    flex: none;
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: var(--b2s-color-border-mid);
  }

  .row__dot.is-healthy {
    background: #22c55e;
    box-shadow: 0 0 0 4px rgba(34, 197, 94, 0.15);
  }

  .row__dot.is-degraded {
    background: var(--b2s-color-warning);
    box-shadow: 0 0 0 4px rgba(245, 158, 11, 0.15);
  }

  .row__dot.is-down {
    background: #ef4444;
    box-shadow: 0 0 0 4px rgba(239, 68, 68, 0.15);
  }

  .row__main {
    min-width: 0;
  }

  .row__main strong,
  .row__main small {
    display: block;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .row__main strong {
    font-size: var(--b2s-fs-sm);
    color: var(--b2s-color-heading);
  }

  .row__main small,
  .row__bar small,
  .row__meta small {
    font-size: var(--b2s-fs-xs);
    color: var(--b2s-color-text-muted);
  }

  .row__bar {
    display: grid;
    gap: 3px;
  }

  .row__meta {
    display: grid;
    justify-items: end;
    gap: 2px;
  }

  .row__latency {
    font-family: var(--b2s-font-mono);
    font-size: var(--b2s-fs-sm);
    color: var(--b2s-color-text);
  }

</style>
