<script lang="ts">
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { t } from '$lib/i18n';
  import Tabs from '$lib/components/ui/Tabs.svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import InfraDatabase from '$lib/components/infrastructure/InfraDatabase.svelte';
  import InfraWorkers from '$lib/components/infrastructure/InfraWorkers.svelte';
  import InfraSchedules from '$lib/components/infrastructure/InfraSchedules.svelte';
  import InfraServices from '$lib/components/infrastructure/InfraServices.svelte';
  import InfraKeycloak from '$lib/components/infrastructure/InfraKeycloak.svelte';
  import { reportUiError } from '$lib/errors';
  import { getInfraOverview, type InfraOverview as Overview, type InfraService } from '$lib/api/infrastructure';

  export let data: { overview: Overview | null; services: InfraService[] };

  let overview: Overview | null = data.overview;
  let services: InfraService[] = data.services ?? [];

  // Platform health lives in Observability › Health; this page only configures
  type TabKey = 'database' | 'workers' | 'keycloak' | 'schedules' | 'components';
  const TAB_KEYS: TabKey[] = ['database', 'workers', 'keycloak', 'schedules', 'components'];

  $: active = (TAB_KEYS.includes($page.url.searchParams.get('tab') as TabKey) ? $page.url.searchParams.get('tab') : 'database') as TabKey;
  $: tabs = [
    { key: 'database', label: t('Database'), icon: 'bi-database' },
    { key: 'workers', label: t('Workers'), icon: 'bi-cpu', count: overview?.workers.length ?? null },
    { key: 'keycloak', label: t('Keycloak'), icon: 'bi-key' },
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
</script>

<div class="infra">
  <Tabs {tabs} activeKey={active} onChange={setTab} ariaLabel={t('Infrastructure')} />

  <p class="infra__hint">
    <i class="bi bi-activity" aria-hidden="true"></i>
    {t('The platform health and its checks are shown in')} <a href="/observability?tab=health">{t('Observability › Health')}</a>.
  </p>

  <div class="infra__body">
    {#if !overview}
      <InlineAlert tone="error">{t('Unable to load the infrastructure state.')}</InlineAlert>
    {:else if active === 'database'}
      <InfraDatabase info={overview.database} onChanged={refresh} />
    {:else if active === 'workers'}
      <InfraWorkers workers={overview.workers} onChanged={refresh} />
    {:else if active === 'keycloak'}
      <InfraKeycloak />
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

  .infra__hint {
    margin: 0;
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-sm);
  }

  .infra__hint i {
    margin-right: 6px;
  }

  .infra__body {
    min-width: 0;
  }
</style>
