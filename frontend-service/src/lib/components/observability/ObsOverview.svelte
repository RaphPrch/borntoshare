<script lang="ts">
  import { t } from '$lib/i18n';
  import { formatDateTime, timeAgo, timeUntil } from '$lib/utils/format';
  import StatusBadge from '$lib/components/ui/StatusBadge.svelte';
  import { formatActivityItem } from '$lib/activity/format';
  import { CATEGORIES } from '$lib/utils/infrastructure';
  import { jobStatusLabel, jobStatusVariant, jobTypeLabel } from '$lib/utils/jobs';
  import type { ObsOverview } from '$lib/api/observability';
  import type { StatusVariant } from '$lib/utils/status';

  export let data: ObsOverview;
  /** Link to a tab of the page, with its filters */
  export let tabHref: (tab: string, params?: Record<string, string>) => string;

  const SEVERITY_VARIANT: Record<string, StatusVariant> = { critical: 'error', high: 'error', warning: 'warning', info: 'info' };
  const severityLabel = (value: string): string =>
    ({ critical: t('Critical'), high: t('High'), warning: t('Warning'), info: t('Info') } as Record<string, string>)[value] ?? value;
  const PERIOD_LABEL: Record<string, () => string> = { '24h': () => t('24 h'), '7d': () => t('7 days'), '30d': () => t('30 days') };
  const CORE_FAMILIES = new Set(['service', 'data', 'queue', 'web']);

  $: health = data.health;
  $: alerts = data.alerts;
  $: jobs = data.jobs;
  $: signIns = data.sign_ins;
  $: periodLabel = PERIOD_LABEL[data.period]?.() ?? data.period;
  $: platformDown = health.down.length > 0 && data.health.families.some((f) => f.down > 0 && CORE_FAMILIES.has(f.key));
  $: state = health.summary.total === 0
    ? 'unknown'
    : platformDown
      ? 'down'
      : health.down.length || health.degraded.length || alerts.critical_open
        ? 'degraded'
        : 'healthy';

  const HERO: Record<string, { title: () => string; icon: string }> = {
    healthy: { title: () => t('All systems operational'), icon: 'bi-check-lg' },
    degraded: { title: () => t('Degraded performance'), icon: 'bi-exclamation-lg' },
    down: { title: () => t('Incident in progress'), icon: 'bi-x-lg' },
    unknown: { title: () => t('State not known yet'), icon: 'bi-question-lg' }
  };

  $: heroText = [
    health.down.length
      ? t('{n} component(s) down ({names})', {
          n: health.down.length,
          names: health.down.slice(0, 2).map((d) => d.label).join(', ') + (health.down.length > 2 ? '…' : '')
        })
      : health.degraded.length
        ? t('{n} component(s) slow', { n: health.degraded.length })
        : health.summary.total
          ? t('Every component answers')
          : t('No health check yet'),
    alerts.critical_open ? t('{n} critical alert(s) to handle', { n: alerts.critical_open }) : t('No critical alert'),
    health.last_check_at ? t('last check {ago}', { ago: timeAgo(health.last_check_at) }) : ''
  ].filter(Boolean).join(' · ');

  $: heroAction = health.down.length
    ? { label: t('See what is down'), href: tabHref('health') }
    : alerts.critical_open
      ? { label: t('See the critical alerts'), href: tabHref('alerts', { severity: 'critical_high' }) }
      : null;

  $: families = CATEGORIES.map((c) => ({ ...c, family: health.families.find((f) => f.key === c.key) })).filter((c) => c.family);

  function eventRow(entry: Record<string, unknown>) {
    const rendered = formatActivityItem(entry as never);
    const outcome = String(entry.outcome ?? '').toLowerCase();
    const failed = ['failure', 'failed', 'error'].includes(outcome);
    const changed = /(created|updated|deleted|added|removed|purged|configured)$/.test(String(entry.action ?? ''));
    return {
      id: String(entry.id ?? ''),
      at: String(entry.created_at ?? ''),
      title: rendered?.title || String(entry.action ?? ''),
      details: rendered?.subtitle1 || '',
      tone: failed ? 'is-err' : changed ? 'is-info' : 'is-ok'
    };
  }

  $: events = data.events.slice(0, 7).map(eventRow);

  const hourOf = (iso: string) => {
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? '' : d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
  };
  const reasonLabel = (code: string): string =>
    ({
      ACCOUNT_NOT_AUTHORIZED: t('account not authorized'),
      NOT_ENTITLED: t('account not authorized'),
      UNAUTHENTICATED: t('wrong password'),
      FORBIDDEN: t('inactive account')
    } as Record<string, string>)[code] ?? code.toLowerCase();
  $: refusedHint = Object.entries(
    Object.entries(signIns.reasons).reduce<Record<string, number>>((acc, [code, n]) => {
      const label = reasonLabel(code);
      acc[label] = (acc[label] ?? 0) + n;
      return acc;
    }, {})
  )
    .map(([label, n]) => `${n} ${label}`)
    .join(' · ');
</script>

<section class={`hero is-${state}`}>
  <span class="hero__icon"><i class={`bi ${HERO[state].icon}`} aria-hidden="true"></i></span>
  <div>
    <h2>{HERO[state].title()}</h2>
    <p>{heroText}</p>
  </div>
  {#if heroAction}
    <a class="b2s-btn b2s-btn-primary hero__action" href={heroAction.href}>{heroAction.label}</a>
  {/if}
</section>

<div class="kpis">
  <a class="kpi" href={tabHref('alerts', { severity: 'critical_high' })}>
    <span class="kpi__label">{t('Critical alerts')}</span>
    <span class="kpi__value"><b class:is-err={alerts.critical_open > 0}>{alerts.critical_open}</b>
      {#if alerts.critical_new}<span class="is-err">{t('+{n} over {period}', { n: alerts.critical_new, period: periodLabel })}</span>{/if}
    </span>
    <span class="kpi__hint">{t('{w} warnings · {a} acknowledged', { w: alerts.warnings_open, a: alerts.acknowledged })}</span>
  </a>
  <a class="kpi" href={tabHref('jobs', { status: 'FAILED' })}>
    <span class="kpi__label">{t('Failed or stuck jobs')}</span>
    <span class="kpi__value"><b class:is-warn={jobs.failed + jobs.stuck > 0}>{jobs.failed + jobs.stuck}</b>
      <span>{t('out of {n} over {period}', { n: jobs.total, period: periodLabel })}</span>
    </span>
    <span class="kpi__hint">{t('{n} queued for more than 5 min', { n: jobs.stuck })}</span>
  </a>
  <a class="kpi" href={tabHref('health')}>
    <span class="kpi__label">{t('Components down')}</span>
    <span class="kpi__value"><b class:is-err={health.down.length > 0}>{health.down.length}</b>
      <span>{t('out of {n} monitored', { n: health.summary.total })}</span>
    </span>
    <span class="kpi__hint">{health.uptime_24h !== null ? t('24 h availability: {pct} %', { pct: health.uptime_24h }) : t('No history yet')}</span>
  </a>
  <a class="kpi" href={tabHref('events', { outcome: 'failure', module: 'auth' })}>
    <span class="kpi__label">{t('Refused sign-ins')}</span>
    <span class="kpi__value"><b>{signIns.refused}</b>
      <span>{t('out of {n} over {period}', { n: signIns.total, period: periodLabel })}</span>
    </span>
    <span class="kpi__hint">{refusedHint || t('None')}</span>
  </a>
</div>

<div class="cols cols--main">
  <section class="panel">
    <header class="panel__head">
      <h3>{t('To handle')}</h3>
      <span>{t('open alerts, grouped')}</span>
      <a href={tabHref('alerts')}>{t('All alerts')}</a>
    </header>
    {#if alerts.groups.length === 0}
      <p class="panel__empty"><i class="bi bi-check2-circle" aria-hidden="true"></i>{t('No open alert. Everything looks fine.')}</p>
    {:else}
      <ul class="rows">
        {#each alerts.groups as group (group.alert_type)}
          <li>
            <a class="row-link" href={tabHref('alerts', { q: group.alert_type })}>
              <StatusBadge compact variant={SEVERITY_VARIANT[group.severity] ?? 'muted'} label={severityLabel(group.severity)} />
              <span class="row-main">
                <strong>{t(group.title)}</strong>
                <small>
                  {#if group.scope_count}{group.scopes.join(', ')}{group.scope_count > group.scopes.length ? ` +${group.scope_count - group.scopes.length}` : ''}{' · '}{/if}{group.example ?? ''}
                </small>
              </span>
              <span class="row-count">× {group.count}</span>
            </a>
          </li>
        {/each}
      </ul>
    {/if}
  </section>

  <section class="panel">
    <header class="panel__head">
      <h3>{t('Recent activity')}</h3>
      <a href={tabHref('events')}>{t('All events')}</a>
    </header>
    {#if events.length === 0}
      <p class="panel__empty">{t('No event yet.')}</p>
    {:else}
      <ol class="timeline">
        {#each events as e (e.id)}
          <li>
            <span class="timeline__time" title={formatDateTime(e.at)}>{hourOf(e.at)}</span>
            <span class={`timeline__dot ${e.tone}`} aria-hidden="true"></span>
            <span><b>{e.title}</b>{#if e.details}{' · '}{e.details}{/if}</span>
          </li>
        {/each}
      </ol>
    {/if}
  </section>
</div>

<div class="cols">
  <section class="panel">
    <header class="panel__head">
      <h3>{t('Jobs')}</h3>
      <span>{t('running and failed')}</span>
      <a href={tabHref('jobs')}>{t('All jobs')}</a>
    </header>
    {#if jobs.items.length === 0}
      <p class="panel__empty"><i class="bi bi-check2-circle" aria-hidden="true"></i>{t('No job running or failed.')}</p>
    {:else}
      <ul class="rows">
        {#each jobs.items as job (job.id)}
          <li class="row-static">
            <StatusBadge compact variant={jobStatusVariant(job.status)} label={jobStatusLabel(job.status)} />
            <span class="row-main">
              <strong>{jobTypeLabel(job.job_type, job.action)}</strong>
              <small>{job.error_message ?? job.error_code ?? `#${job.id}`}</small>
            </span>
            <span class="row-time" title={formatDateTime(job.updated_at)}>{timeAgo(job.updated_at)}</span>
          </li>
        {/each}
      </ul>
    {/if}
  </section>

  <section class="panel">
    <header class="panel__head">
      <h3>{t('Platform health')}</h3>
      {#if health.next_check_at}<span>{t('next check {when}', { when: timeUntil(health.next_check_at) })}</span>{/if}
      <a href={tabHref('health')}>{t('Detail per component')}</a>
    </header>
    {#if families.length === 0}
      <p class="panel__empty">{t('No health check yet.')}</p>
    {:else}
      <div class="families">
        {#each families as item (item.key)}
          <a class={`family is-${item.family?.status}`} href={tabHref('health')}>
            <span class="family__dot" aria-hidden="true"></span>
            {item.label()}
            <span class="family__count">{item.family?.up}/{item.family?.total}</span>
          </a>
        {/each}
      </div>
    {/if}
  </section>
</div>

<style>
  .hero {
    display: grid;
    grid-template-columns: auto 1fr auto;
    gap: 16px;
    align-items: center;
    padding: 18px 22px;
    border: 1px solid;
    border-radius: var(--b2s-radius-md);
    margin-bottom: 14px;
  }

  .hero.is-healthy {
    background: var(--b2s-color-success-soft);
    border-color: var(--b2s-color-success-border);
  }

  .hero.is-degraded {
    background: #fffbeb;
    border-color: #fde68a;
  }

  .hero.is-down {
    background: var(--b2s-color-danger-soft);
    border-color: var(--b2s-color-danger-border);
  }

  .hero.is-unknown {
    background: var(--b2s-color-surface-soft);
    border-color: var(--b2s-color-border-soft);
  }

  .hero__icon {
    width: 44px;
    height: 44px;
    border-radius: 50%;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    color: #ffffff;
    font-size: 1.35rem;
    background: var(--b2s-color-text-faint);
  }

  .is-healthy .hero__icon {
    background: var(--b2s-color-success);
  }

  .is-degraded .hero__icon {
    background: var(--b2s-color-warning);
  }

  .is-down .hero__icon {
    background: var(--b2s-color-danger);
  }

  .hero h2 {
    margin: 0;
    font-size: 19px;
    font-weight: 600;
    color: var(--b2s-color-heading);
  }

  .hero p {
    margin: 4px 0 0;
    font-size: var(--b2s-fs-md);
    color: var(--b2s-color-text-soft);
  }

  .kpis {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 12px;
    margin-bottom: 14px;
  }

  .kpi {
    display: grid;
    gap: 4px;
    padding: 16px 18px;
    border: 1px solid var(--b2s-color-border-soft);
    border-radius: var(--b2s-radius-md);
    background: var(--b2s-color-surface);
    color: var(--b2s-color-heading);
    text-decoration: none;
    transition: border-color 0.15s ease, box-shadow 0.15s ease;
  }

  .kpi:hover {
    border-color: var(--b2s-color-text-faint);
    box-shadow: 0 4px 14px rgba(15, 23, 42, 0.06);
    color: var(--b2s-color-heading);
  }

  .kpi__label {
    font-size: var(--b2s-fs-sm);
    color: var(--b2s-color-text-soft);
  }

  .kpi__value {
    display: flex;
    align-items: baseline;
    gap: 8px;
    flex-wrap: wrap;
    font-size: var(--b2s-fs-sm);
    color: var(--b2s-color-text-soft);
  }

  .kpi__value b {
    font-size: 30px;
    font-weight: 600;
    color: var(--b2s-color-heading);
  }

  .kpi__hint {
    font-size: var(--b2s-fs-xs);
    color: var(--b2s-color-text-muted);
  }

  .is-err {
    color: var(--b2s-color-danger-strong) !important;
  }

  .is-warn {
    color: var(--b2s-color-warning-strong) !important;
  }

  .cols {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 14px;
    align-items: start;
    margin-bottom: 14px;
  }

  .cols--main {
    grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr);
  }

  .panel {
    border: 1px solid var(--b2s-color-border-soft);
    border-radius: var(--b2s-radius-md);
    background: var(--b2s-color-surface);
    overflow: hidden;
  }

  .panel__head {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 14px 18px;
    border-bottom: 1px solid var(--b2s-color-border-soft);
  }

  .panel__head h3 {
    margin: 0;
    font-size: 15px;
    font-weight: 600;
    color: var(--b2s-color-heading);
  }

  .panel__head span {
    font-size: var(--b2s-fs-xs);
    color: var(--b2s-color-text-muted);
  }

  .panel__head a {
    margin-left: auto;
    font-size: var(--b2s-fs-sm);
  }

  .panel__empty {
    margin: 0;
    padding: 22px 18px;
    display: flex;
    gap: 8px;
    align-items: center;
    color: var(--b2s-color-text-soft);
    font-size: var(--b2s-fs-sm);
  }

  .panel__empty i {
    color: var(--b2s-color-success);
  }

  .rows {
    list-style: none;
    margin: 0;
    padding: 0;
  }

  .rows li + li {
    border-top: 1px solid var(--b2s-color-neutral-soft);
  }

  .row-link,
  .row-static {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    gap: 12px;
    align-items: center;
    padding: 12px 18px;
    color: var(--b2s-color-heading);
    text-decoration: none;
  }

  .row-link:hover {
    background: var(--b2s-color-surface-soft);
    color: var(--b2s-color-heading);
  }

  .row-main strong,
  .row-main small {
    display: block;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .row-main strong {
    font-size: var(--b2s-fs-md);
    font-weight: 600;
  }

  .row-main small {
    font-size: var(--b2s-fs-xs);
    color: var(--b2s-color-text-muted);
  }

  .row-count {
    font-size: var(--b2s-fs-sm);
    font-weight: 600;
    color: var(--b2s-color-text-soft);
  }

  .row-time {
    font-size: var(--b2s-fs-xs);
    color: var(--b2s-color-text-muted);
    white-space: nowrap;
  }

  .timeline {
    list-style: none;
    margin: 0;
    padding: 4px 18px 10px;
  }

  .timeline li {
    display: grid;
    grid-template-columns: auto auto minmax(0, 1fr);
    gap: 10px;
    align-items: start;
    padding: 8px 0;
    font-size: var(--b2s-fs-sm);
    color: var(--b2s-color-text-strong);
  }

  .timeline__time {
    color: var(--b2s-color-text-muted);
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
  }

  .timeline__dot {
    width: 8px;
    height: 8px;
    margin-top: 6px;
    border-radius: 50%;
    background: var(--b2s-color-success);
  }

  .timeline__dot.is-err {
    background: var(--b2s-color-danger);
  }

  .timeline__dot.is-info {
    background: var(--b2s-color-info);
  }

  .timeline b {
    color: var(--b2s-color-heading);
  }

  .families {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
    padding: 14px 18px;
  }

  .family {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    border-radius: var(--b2s-radius-sm);
    background: var(--b2s-color-surface-soft);
    font-size: var(--b2s-fs-sm);
    color: var(--b2s-color-heading);
    text-decoration: none;
  }

  .family:hover {
    color: var(--b2s-color-heading);
    background: var(--b2s-color-neutral-soft);
  }

  .family__dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: #22c55e;
  }

  .family.is-down {
    background: var(--b2s-color-danger-soft);
  }

  .family.is-down .family__dot {
    background: #ef4444;
  }

  .family.is-degraded .family__dot {
    background: var(--b2s-color-warning);
  }

  .family.is-unknown .family__dot {
    background: var(--b2s-color-border-mid);
  }

  .family__count {
    margin-left: auto;
    color: var(--b2s-color-text-muted);
  }

  .family.is-down .family__count {
    color: var(--b2s-color-danger-strong);
    font-weight: 600;
  }

  @media (max-width: 1000px) {
    .kpis {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .cols,
    .cols--main {
      grid-template-columns: 1fr;
    }
  }

</style>
