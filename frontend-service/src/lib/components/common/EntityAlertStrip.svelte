<script lang="ts">
  import type { EntityAlertStripItem } from '$lib/components/common/entity-alerts.types';

  export let items: EntityAlertStripItem[] = [];
  export let onViewAll: () => void = () => {};
  export let ariaLabel = 'Entity alerts';

  $: visibleItems = items.slice(0, 4);
  $: hiddenCount = Math.max(0, items.length - visibleItems.length);
</script>

{#if items.length > 0}
  <section class="sr-clean-alert-strip" aria-label={ariaLabel}>
    <div class="sr-clean-alert-strip__items">
      {#each visibleItems as item (item.key)}
        <article class={`sr-clean-alert-strip__item is-${item.tone ?? 'warning'}`}>
          <span class="sr-clean-alert-strip__icon">
            <i class={`bi ${item.tone === 'error' ? 'bi-x-circle-fill' : 'bi-exclamation-triangle-fill'}`} aria-hidden="true"></i>
          </span>
          <div>
            <strong>{item.title}</strong>
            {#if item.subtitle}
              <small>{item.subtitle}</small>
            {/if}
          </div>
        </article>
      {/each}
    </div>

    <button type="button" class="sr-clean-alert-strip__link" on:click={onViewAll}>
      View all alerts ({items.length})
      {#if hiddenCount > 0}
        <span class="visually-hidden">, including {hiddenCount} hidden alerts</span>
      {/if}
      <i class="bi bi-chevron-right" aria-hidden="true"></i>
    </button>
  </section>
{/if}
