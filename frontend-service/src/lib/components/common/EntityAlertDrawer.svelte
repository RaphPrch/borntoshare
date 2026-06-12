<script lang="ts">
  import EntityDrawerShell from '$lib/components/common/EntityDrawerShell.svelte';
  import type { EntityAlertStripItem } from '$lib/components/common/entity-alerts.types';

  export let open = false;
  export let title = 'Alerts';
  export let subtitle: string | null = null;
  export let items: EntityAlertStripItem[] = [];
  export let emptyLabel = 'No alert found.';
  export let onClose: () => void = () => {};
  export let ariaLabelledby = 'entity-alerts-drawer-title';
  export let width = '640px';
  export let topOffset = '70px';
</script>

<EntityDrawerShell
  {open}
  {title}
  {subtitle}
  {onClose}
  {ariaLabelledby}
  {width}
  {topOffset}
  showFooter={false}
>
  {#if items.length === 0}
    <div class="sr-loading-state empty">{emptyLabel}</div>
  {:else}
    <div class="sr-alerts-drawer-list">
      {#each items as alert (alert.key)}
        <article class={`sr-alerts-drawer-row is-${alert.tone ?? 'warning'}`}>
          <span class="sr-alerts-drawer-row__icon">
            <i class={`bi ${alert.tone === 'error' ? 'bi-x-circle-fill' : 'bi-exclamation-triangle-fill'}`} aria-hidden="true"></i>
          </span>
          <div>
            <strong>{alert.title}</strong>
            {#if alert.subtitle}
              <small>{alert.subtitle}</small>
            {/if}
          </div>
        </article>
      {/each}
    </div>
  {/if}
</EntityDrawerShell>
