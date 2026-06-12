<script lang="ts">
  export type EntityKpiItem = {
    key: string;
    label: string;
    value: string;
    hint?: string;
    tone?: 'neutral' | 'info' | 'success' | 'warning' | 'danger' | 'accent';
    icon?: string;
  };

  export let items: EntityKpiItem[] = [];
  export let ariaLabel = 'Entity KPIs';
</script>

<section class="sed-kpi-row" aria-label={ariaLabel}>
  {#each items as item (item.key)}
    <article class={`sed-kpi-card sed-kpi-card--${item.tone ?? 'neutral'}`}>
      <div class="sed-kpi-card__head">
        <span class="sed-kpi-label">{item.label}</span>
        {#if item.icon}
          <span class="sed-kpi-icon-wrap" aria-hidden="true">
            <i class={`bi ${item.icon} sed-kpi-icon`}></i>
          </span>
        {/if}
      </div>
      <div class="sed-kpi-value">{item.value}</div>
      {#if item.hint}
        <div class="sed-kpi-hint">{item.hint}</div>
      {/if}
    </article>
  {/each}
</section>
