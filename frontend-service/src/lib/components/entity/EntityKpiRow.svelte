<script module lang="ts">
  export type EntityKpiItem = {
    key: string;
    label: string;
    value: string;
    hint?: string;
    tone?: 'neutral' | 'info' | 'success' | 'warning' | 'danger' | 'accent';
    icon?: string;
  };
</script>

<script lang="ts">
  import { t } from '$lib/i18n';
  import KpiCard from '$lib/components/ui/KpiCard.svelte';

  export let items: EntityKpiItem[] = [];
  export let ariaLabel = t('Entity KPIs');

  const KPI_TONES = { neutral: 'neutral', info: 'info', success: 'success', warning: 'warning', danger: 'danger', accent: 'purple' } as const;
</script>

<section class="b2s-kpi-grid entity-kpis" aria-label={ariaLabel}>
  {#each items as item (item.key)}
    <KpiCard
      label={item.label}
      value={item.value}
      hint={item.hint ?? null}
      icon={item.icon ?? 'bi-dot'}
      tone={KPI_TONES[item.tone ?? 'neutral']}
    />
  {/each}
</section>

<style>
  .entity-kpis {
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  }
</style>
