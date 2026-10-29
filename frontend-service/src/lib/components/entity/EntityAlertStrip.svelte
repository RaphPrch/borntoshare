<script lang="ts">
  import { t } from '$lib/i18n';
  import type { EntityAlertStripItem } from '$lib/components/entity/entity-alerts.types';

  /** Alerts of the selected entity, shown under its header (first ones + link to the full list). */
  export let items: EntityAlertStripItem[] = [];
  export let onViewAll: () => void = () => {};
  export let ariaLabel = t('Entity alerts');
  /** What fixes the main alert (e.g. edit the connection), shown next to it */
  export let action: { label: string; icon?: string; onClick: () => void } | null = null;

  $: visibleItems = items.slice(0, 2);
  $: hasError = items.some((item) => item.tone === 'error');
</script>

{#if items.length > 0}
  <section class="entity-alerts" class:is-error={hasError} aria-label={ariaLabel}>
    <i class={`bi ${hasError ? 'bi-exclamation-octagon' : 'bi-exclamation-triangle'} entity-alerts__icon`} aria-hidden="true"></i>
    <ul class="entity-alerts__items">
      {#each visibleItems as item (item.key)}
        <li>
          <strong>{item.title}</strong>
          {#if item.subtitle}<span>{item.subtitle}</span>{/if}
        </li>
      {/each}
    </ul>
    {#if action}
      <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm entity-alerts__action" on:click={action.onClick}>
        {#if action.icon}<i class={`bi ${action.icon}`} aria-hidden="true"></i>{/if}
        {action.label}
      </button>
    {/if}
    <button type="button" class="entity-alerts__link" on:click={onViewAll}>
      {items.length > visibleItems.length
        ? t('View all alerts ({itemsCount})', { itemsCount: items.length })
        : t('Details')}
      <i class="bi bi-chevron-right" aria-hidden="true"></i>
    </button>
  </section>
{/if}

<style>
  .entity-alerts__action {
    flex: none;
    align-self: center;
  }

  .entity-alerts {
    display: flex;
    align-items: flex-start;
    gap: 12px;
    padding: 12px 16px;
    border: 1px solid var(--b2s-color-warning-border);
    border-radius: var(--b2s-radius-md);
    background: var(--b2s-color-warning-soft);
    color: #9a3412;
    font-size: var(--b2s-fs-sm);
  }

  .entity-alerts.is-error {
    border-color: var(--b2s-color-danger-border);
    background: var(--b2s-color-danger-soft);
    color: var(--b2s-color-danger-strong);
  }

  .entity-alerts__icon {
    font-size: var(--b2s-fs-lg);
    line-height: 1.3;
  }

  .entity-alerts__items {
    flex: 1 1 auto;
    min-width: 0;
    display: grid;
    gap: 4px;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .entity-alerts__items strong {
    font-weight: 600;
  }

  .entity-alerts__items span {
    margin-left: 8px;
    opacity: 0.8;
  }

  .entity-alerts__link {
    flex: 0 0 auto;
    display: inline-flex;
    align-items: center;
    gap: 4px;
    border: none;
    background: transparent;
    color: inherit;
    font-size: var(--b2s-fs-sm);
    font-weight: 600;
    cursor: pointer;
    white-space: nowrap;
  }

  .entity-alerts__link:hover {
    text-decoration: underline;
  }
</style>
