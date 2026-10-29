<script lang="ts">
  import { t } from '$lib/i18n';
  import { breakable } from '$lib/utils/format';
  import EntityProperties from "$lib/components/entity/EntityProperties.svelte";
  import EntityProperty from "$lib/components/entity/EntityProperty.svelte";
  import ZoneEndpointsTable from "../components/ZoneEndpointsTable.svelte";

  /** Overview of a zone on one surface: its file servers and an inspector of its properties. */
  export let zone: any;
  export let endpoints: any[] = [];
  export let storageRootCount = 0;
  export let namingTemplateLabel = '';
  export let provisioningOu = '';
  export let probeResultsByEndpoint: Record<string, string> = {};
  export let onCreateEndpoint: (() => void) | null = null;
  export let onRunEndpointProbe: ((endpoint: any) => void) | null = null;
</script>

<div class="zo">
  <section class="zo__main" aria-label={t('Storage endpoints')}>
    <div class="zo__head">
      <h2>{t('Storage endpoints')}</h2>
      <button type="button" class="b2s-panel__link" on:click={() => onCreateEndpoint?.()}>{t('Add endpoint')}</button>
    </div>
    <ZoneEndpointsTable {endpoints} {probeResultsByEndpoint} onRunProbe={onRunEndpointProbe} />
  </section>

  <EntityProperties title={t('Properties')}>
    <EntityProperty label={t('Code')}>{zone?.code ?? '—'}</EntityProperty>
    <EntityProperty label={t('Storage roots')}>{storageRootCount}</EntityProperty>
    <EntityProperty label={t('Naming template')} mono>{breakable(namingTemplateLabel) || '—'}</EntityProperty>
    <EntityProperty label={t('Provisioning OU')}>{breakable(provisioningOu) || '—'}</EntityProperty>
  </EntityProperties>
</div>

<style>
  .zo {
    display: flex;
    flex-wrap: wrap;
    gap: 40px;
    align-items: flex-start;
  }

  .zo__main {
    flex: 999 1 420px;
    min-width: 0;
    display: grid;
    gap: 12px;
  }

  .zo__head {
    display: flex;
    align-items: baseline;
    gap: 12px;
  }

  h2 {
    margin: 0;
    font-size: var(--b2s-fs-md);
    font-weight: 600;
  }
</style>
