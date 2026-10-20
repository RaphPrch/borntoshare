<script lang="ts">
  import { t } from '$lib/i18n';
  import EntityOverviewPanel from "$lib/components/entity/EntityOverviewPanel.svelte";
  import EntityKpiRow from "$lib/components/entity/EntityKpiRow.svelte";
  import type { EntityKpiItem } from '$lib/components/entity/EntityKpiRow.svelte';
  import EntityOverviewLayout from "$lib/components/entity/EntityOverviewLayout.svelte";
  import ZoneEndpointsTable from "../components/ZoneEndpointsTable.svelte";
  import RecentActivityCard from "$lib/components/activity/RecentActivityCard.svelte";

  export let zone: any;
  export let endpoints: any[] = [];
  export let storageRootCount = 0;
  export let probeResultsByEndpoint: Record<string, string> = {};
  export let activity: any[] = [];
  export let healthSummary: {
    endpointCount: number;
    reachableCount: number;
    runnableCount?: number;
    nonRunnableCount?: number;
    lastProbeAt: string | null;
    unhealthyCount?: number;
    healthLabel?: "ok" | "warning";
  };

  export let onCreateEndpoint: (() => void) | null = null;
  export let onRunEndpointProbe: ((endpoint: any) => void) | null = null;
  export let onViewAllActivity: (() => void) | null = null;
  export let onSelectActivity: ((entry: any) => void) | null = null;

  $: availabilityRate = healthSummary.endpointCount > 0
    ? `${Math.round((healthSummary.reachableCount / healthSummary.endpointCount) * 100)}%`
    : "0%";
  let reachabilityTone: EntityKpiItem["tone"] = "neutral";
  $: reachabilityTone = healthSummary.endpointCount === 0
    ? "neutral"
    : (healthSummary.unhealthyCount ?? 0) > 0
      ? "danger"
      : "success";

  let kpis: EntityKpiItem[] = [];
  $: kpis = [
    {
      key: "endpoints",
      label: "Endpoints",
      value: String(endpoints.length),
      tone: "info",
      icon: "bi-hdd-network"
    },
    {
      key: "roots",
      label: "Storage roots",
      value: String(storageRootCount),
      tone: "neutral",
      icon: "bi-diagram-3"
    },
    {
      key: "reachability",
      label: "Reachability",
      value: availabilityRate,
      hint: t('{reachableCount}/{value} reachable', { reachableCount: healthSummary.reachableCount, value: (healthSummary.endpointCount || 0) }),
      tone: reachabilityTone,
      icon: "bi-heart-pulse"
    }
  ];

  $: latestActivity = activity.slice(0, 5);
</script>

<div class="zone-console__stack">
  <EntityOverviewLayout>
    <svelte:fragment slot="main">
      <EntityOverviewPanel title={t('Overview KPIs')} bodyClass="p-3">
        <EntityKpiRow items={kpis} ariaLabel={t('Zone KPIs')} />
      </EntityOverviewPanel>

      <EntityOverviewPanel title={t('Endpoints')} headClass="sed-panel__head--toolbar" bodyClass="p-3 pt-2">
        <svelte:fragment slot="actions">
          <button type="button" class="zone-console__btn-ghost" on:click={() => onCreateEndpoint?.()}>
            {t('Add endpoint')}
          </button>
        </svelte:fragment>
        <ZoneEndpointsTable {endpoints} {probeResultsByEndpoint} onRunProbe={onRunEndpointProbe} />
      </EntityOverviewPanel>
    </svelte:fragment>

    <svelte:fragment slot="side">
      <RecentActivityCard
        title={t('Recent activity')}
        items={latestActivity}
        max={5}
        onViewAll={onViewAllActivity}
        onSelect={onSelectActivity}
      />
    </svelte:fragment>
  </EntityOverviewLayout>
</div>
