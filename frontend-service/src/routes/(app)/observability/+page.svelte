<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { t } from '$lib/i18n';
  import PageHeader from '$lib/components/ui/PageHeader.svelte';
  import Tabs from '$lib/components/ui/Tabs.svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import ObsOverview from '$lib/components/observability/ObsOverview.svelte';
  import ObsAlerts from '$lib/components/observability/ObsAlerts.svelte';
  import ObsEvents from '$lib/components/observability/ObsEvents.svelte';
  import ObsJobs from '$lib/components/observability/ObsJobs.svelte';
  import InfraOverview from '$lib/components/infrastructure/InfraOverview.svelte';
  import { toast } from '$lib/stores/toast';
  import { reportUiError } from '$lib/errors';
  import { getObservabilityOverview, type ObsOverview as Overview, type ObsPeriod } from '$lib/api/observability';
  import { getInfraOverview, runSchedule, type InfraOverview as InfraData } from '$lib/api/infrastructure';

  export let data: { period: ObsPeriod; overview: Overview | null; infra: InfraData | null };

  type TabKey = 'overview' | 'alerts' | 'events' | 'jobs' | 'health';
  const TAB_KEYS: TabKey[] = ['overview', 'alerts', 'events', 'jobs', 'health'];

  let overview: Overview | null = data.overview;
  let infra: InfraData | null = data.infra;
  let period: ObsPeriod = data.period;
  let refreshing = false;
  let checking = false;
  let timer: ReturnType<typeof setInterval> | null = null;

  $: params = $page.url.searchParams;
  $: active = (TAB_KEYS.includes(params.get('tab') as TabKey) ? params.get('tab') : 'overview') as TabKey;
  $: tabs = [
    { key: 'overview', label: t('Overview'), icon: 'bi-speedometer2' },
    { key: 'alerts', label: t('Alerts'), icon: 'bi-exclamation-triangle', count: overview?.alerts.critical_open || null },
    { key: 'events', label: t('Events'), icon: 'bi-list-ul' },
    { key: 'jobs', label: t('Jobs'), icon: 'bi-activity', count: overview ? overview.jobs.failed + overview.jobs.stuck || null : null },
    { key: 'health', label: t('Health'), icon: 'bi-heart-pulse', count: overview?.health.down.length || null }
  ];

  /** A tab with its filters, the period kept */
  function tabHref(tab: string, extra: Record<string, string> = {}): string {
    const search = new URLSearchParams({ tab, ...(period !== '24h' ? { period } : {}), ...extra });
    return `/observability?${search.toString()}`;
  }

  function setTab(key: string) {
    goto(tabHref(key), { noScroll: true, keepFocus: true });
  }

  async function setPeriod(value: ObsPeriod) {
    period = value;
    const url = new URL($page.url);
    if (value === '24h') url.searchParams.delete('period');
    else url.searchParams.set('period', value);
    await goto(url, { replaceState: true, noScroll: true, keepFocus: true });
    await refresh();
  }

  async function refresh() {
    refreshing = true;
    try {
      [overview, infra] = await Promise.all([getObservabilityOverview(fetch, period), getInfraOverview(fetch)]);
    } catch (e) {
      reportUiError(e, t('Unable to load the observability data.'), 'observability.refresh');
    } finally {
      refreshing = false;
    }
  }

  async function runHealthCheck() {
    checking = true;
    try {
      await runSchedule(fetch, 'health_check');
      toast.info(t('Health check started: the worker results arrive in a few seconds.'));
      await refresh();
      setTimeout(refresh, 6000);
      setTimeout(refresh, 15000);
    } catch (e) {
      reportUiError(e, t('Unable to run the health check.'), 'observability.health_check');
    } finally {
      checking = false;
    }
  }

  onMount(() => {
    // Overview and health stay current while the page is open
    timer = setInterval(() => {
      if ((active === 'overview' || active === 'health') && document.visibilityState === 'visible') void refresh();
    }, 30000);
  });
  onDestroy(() => {
    if (timer) clearInterval(timer);
  });
</script>

<div class="obs-page">
  <PageHeader title={t('Monitoring')} subtitle={t('Platform health, alerts, events and jobs in one place.')}>
    <svelte:fragment slot="actions">
      <label class="obs-period">
        <span>{t('Period')}</span>
        <select class="b2s-select" value={period} on:change={(e) => setPeriod(e.currentTarget.value as ObsPeriod)}>
          <option value="24h">{t('Last 24 h')}</option>
          <option value="7d">{t('7 days')}</option>
          <option value="30d">{t('30 days')}</option>
        </select>
      </label>
      <button class="b2s-btn b2s-btn-secondary" type="button" on:click={refresh} disabled={refreshing}>
        <i class={`bi ${refreshing ? 'bi-hourglass-split' : 'bi-arrow-clockwise'}`} aria-hidden="true"></i>{t('Refresh')}
      </button>
    </svelte:fragment>
  </PageHeader>

  <Tabs {tabs} activeKey={active} onChange={setTab} ariaLabel={t('Observability')} />

  <div class="obs-body">
    {#if active === 'overview'}
      {#if overview}
        <ObsOverview data={overview} {tabHref} />
      {:else}
        <InlineAlert tone="error">{t('Unable to load the observability data.')}</InlineAlert>
      {/if}
    {:else if active === 'alerts'}
      {#key `${params.get('severity')}|${params.get('q')}`}
        <ObsAlerts initialSeverity={params.get('severity') ?? 'all'} initialType={params.get('q') ?? ''} />
      {/key}
    {:else if active === 'events'}
      {#key `${period}|${params.get('outcome')}|${params.get('module')}`}
        <ObsEvents {period} initialOutcome={(params.get('outcome') ?? '') as '' | 'success' | 'failure'} initialModule={params.get('module') ?? ''} />
      {/key}
    {:else if active === 'jobs'}
      {#key params.get('status')}
        <ObsJobs initialStatus={params.get('status') ?? 'all'} />
      {/key}
    {:else if infra}
      <InfraOverview overview={infra} running={checking} onRunHealthCheck={runHealthCheck} />
      <p class="obs-note">
        {t('Database, workers, schedules and monitored components are set in')}
        <a href="/admin/advanced-settings/infrastructure">{t('Advanced Settings › Infrastructure')}</a>.
      </p>
    {:else}
      <InlineAlert tone="error">{t('Unable to load the infrastructure state.')}</InlineAlert>
    {/if}
  </div>
</div>

<style>
  .obs-page {
    display: grid;
    gap: 16px;
    padding: var(--b2s-page-padding);
  }

  .obs-body {
    min-width: 0;
  }

  .obs-period {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-size: var(--b2s-fs-sm);
    color: var(--b2s-color-text-soft);
  }

  .obs-note {
    margin: 12px 0 0;
    font-size: var(--b2s-fs-sm);
    color: var(--b2s-color-text-muted);
  }
</style>
