<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { t } from '$lib/i18n';
  import Tabs from '$lib/components/ui/Tabs.svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import InfraOverview from '$lib/components/infrastructure/InfraOverview.svelte';
  import InfraDatabase from '$lib/components/infrastructure/InfraDatabase.svelte';
  import InfraWorkers from '$lib/components/infrastructure/InfraWorkers.svelte';
  import InfraSchedules from '$lib/components/infrastructure/InfraSchedules.svelte';
  import InfraServices from '$lib/components/infrastructure/InfraServices.svelte';
  import { toast } from '$lib/stores/toast';
  import { reportUiError } from '$lib/errors';
  import { getInfraOverview, runSchedule, type InfraOverview as Overview, type InfraService } from '$lib/api/infrastructure';

  export let data: { overview: Overview | null; services: InfraService[] };

  let overview: Overview | null = data.overview;
  let services: InfraService[] = data.services ?? [];
  let checking = false;
  let refreshTimer: ReturnType<typeof setInterval> | null = null;

  type TabKey = 'overview' | 'database' | 'workers' | 'schedules' | 'components';
  const TAB_KEYS: TabKey[] = ['overview', 'database', 'workers', 'schedules', 'components'];

  $: active = (TAB_KEYS.includes($page.url.searchParams.get('tab') as TabKey) ? $page.url.searchParams.get('tab') : 'overview') as TabKey;
  $: tabs = [
    { key: 'overview', label: t('Overview'), icon: 'bi-speedometer2', count: overview ? (overview.summary.down || null) : null },
    { key: 'database', label: t('Database'), icon: 'bi-database' },
    { key: 'workers', label: t('Workers'), icon: 'bi-cpu', count: overview?.workers.length ?? null },
    { key: 'schedules', label: t('Schedules'), icon: 'bi-calendar-check' },
    { key: 'components', label: t('Monitored components'), icon: 'bi-broadcast' }
  ];

  function setTab(key: string) {
    const url = new URL($page.url);
    url.searchParams.set('tab', key);
    goto(url, { replaceState: true, noScroll: true, keepFocus: true });
  }

  async function refresh() {
    try {
      overview = await getInfraOverview(fetch);
    } catch (e) {
      reportUiError(e, t('Unable to load the infrastructure state.'), 'infrastructure.refresh');
    }
  }

  async function runHealthCheck() {
    checking = true;
    try {
      const result = await runSchedule(fetch, 'health_check');
      toast.info(t('Health check started: the worker results arrive in a few seconds.'));
      if (result.status === 'failed') toast.error(result.message);
      await refresh();
      // Results of the worker part land a few seconds later
      setTimeout(refresh, 6000);
      setTimeout(refresh, 15000);
    } catch (e) {
      reportUiError(e, t('Unable to run the health check.'), 'infrastructure.health_check');
    } finally {
      checking = false;
    }
  }

  onMount(() => {
    // The overview stays current while the page is open
    refreshTimer = setInterval(() => {
      if (active === 'overview' && document.visibilityState === 'visible') void refresh();
    }, 30000);
  });
  onDestroy(() => {
    if (refreshTimer) clearInterval(refreshTimer);
  });
</script>

<div class="infra">
  <Tabs {tabs} activeKey={active} onChange={setTab} ariaLabel={t('Infrastructure')} />

  <div class="infra__body">
    {#if !overview}
      <InlineAlert tone="error">{t('Unable to load the infrastructure state.')}</InlineAlert>
    {:else if active === 'overview'}
      <InfraOverview {overview} running={checking} onRunHealthCheck={runHealthCheck} />
    {:else if active === 'database'}
      <InfraDatabase info={overview.database} onChanged={refresh} />
    {:else if active === 'workers'}
      <InfraWorkers workers={overview.workers} onChanged={refresh} />
    {:else if active === 'schedules'}
      <InfraSchedules schedules={overview.schedules} onChanged={refresh} />
    {:else}
      <InfraServices bind:services />
    {/if}
  </div>
</div>

<style>
  .infra {
    display: grid;
    gap: 16px;
  }

  .infra__body {
    min-width: 0;
  }
</style>
