<script lang="ts">
  import { t } from '$lib/i18n';
  import { breakable } from '$lib/utils/format';
  import EntityOverviewPanel from "$lib/components/entity/EntityOverviewPanel.svelte";
  import EntityOverviewLayout from "$lib/components/entity/EntityOverviewLayout.svelte";
  import ZoneEndpointsTable from "../components/ZoneEndpointsTable.svelte";
  import RecentActivityCard from "$lib/components/activity/RecentActivityCard.svelte";

  export let zone: any;
  export let endpoints: any[] = [];
  export let storageRootCount = 0;
  export let namingTemplateLabel = '';
  export let provisioningOu = '';
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


  $: latestActivity = activity.slice(0, 5);
</script>

<div class="zone-console__stack">
  <EntityOverviewLayout>
    <svelte:fragment slot="main">
      <EntityOverviewPanel title={t('Storage endpoints')}>
        <svelte:fragment slot="actions">
          <button type="button" class="b2s-panel__link" on:click={() => onCreateEndpoint?.()}>
            {t('Add endpoint')}
          </button>
        </svelte:fragment>
        <ZoneEndpointsTable {endpoints} {probeResultsByEndpoint} onRunProbe={onRunEndpointProbe} />
      </EntityOverviewPanel>
    </svelte:fragment>

    <svelte:fragment slot="side">
      <article class="b2s-panel">
        <div class="b2s-panel__head"><h2>{t('Details')}</h2></div>
        <div class="b2s-panel__body">
          <dl class="b2s-kv">
            <dt>{t('Code')}</dt><dd>{zone?.code ?? '—'}</dd>
            <dt>{t('Storage roots')}</dt><dd>{storageRootCount}</dd>
            <dt>{t('Naming template')}</dt><dd class="zone-overview__mono">{breakable(namingTemplateLabel) || '—'}</dd>
            <dt>{t('Provisioning OU')}</dt><dd>{breakable(provisioningOu) || '—'}</dd>
          </dl>
        </div>
      </article>
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

<style>
  .zone-overview__mono {
    font-family: var(--b2s-font-mono);
    font-size: var(--b2s-fs-xs);
  }
</style>
