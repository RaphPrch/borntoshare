<script lang="ts">
  interface Props {
    title?: string;
    subtitle?: string | null;
    tertiary?: string | null;
    typeLabel?: string | null;
    compact?: boolean;
    className?: string;
    icon?: import('svelte').Snippet;
    actions?: import('svelte').Snippet;
  }

  let {
    title = '',
    subtitle = null,
    tertiary = null,
    typeLabel = null,
    compact = false,
    className = '',
    icon,
    actions
  }: Props = $props();
</script>

<article class={`b2s-entity-row-card ${compact ? 'is-compact' : ''} ${className}`.trim()}>
  {@render icon?.()}

  <div class="b2s-entity-row-card__content">
    <div class="b2s-entity-row-card__title-row">
      <strong>{title}</strong>
      {#if typeLabel}
        <span class="b2s-entity-row-card__type">{typeLabel}</span>
      {/if}
    </div>

    {#if subtitle}
      <div class="b2s-entity-row-card__meta">{subtitle}</div>
    {/if}

    {#if tertiary}
      <div class="b2s-entity-row-card__submeta">{tertiary}</div>
    {/if}
  </div>

  <div class="b2s-entity-row-card__actions">
    {@render actions?.()}
  </div>
</article>

<style>
  .b2s-entity-row-card {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    padding: 18px 20px;
    border: 1px solid #e3e8f3;
    border-radius: var(--b2s-radius-lg);
    background: var(--b2s-color-surface-soft);
  }

  .b2s-entity-row-card.is-compact {
    padding: 10px 12px;
    border-radius: var(--b2s-radius-md);
    gap: 10px;
  }

  .b2s-entity-row-card__content {
    min-width: 0;
    display: grid;
    gap: 4px;
    flex: 1;
  }

  .b2s-entity-row-card__title-row {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
  }

  .b2s-entity-row-card__title-row strong {
    font-size: var(--b2s-fs-lg);
    font-weight: 700;
    color: #101828;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .b2s-entity-row-card.is-compact .b2s-entity-row-card__title-row strong {
    font-size: var(--b2s-fs-md);
  }

  .b2s-entity-row-card__type {
    height: 22px;
    padding: 0 10px;
    border-radius: var(--b2s-radius-pill);
    border: 1px solid #d8e0ef;
    background: #f4f7fc;
    color: #475467;
    font-size: var(--b2s-fs-xs);
    font-weight: 700;
    display: inline-flex;
    align-items: center;
    flex: 0 0 auto;
  }

  .b2s-entity-row-card__meta,
  .b2s-entity-row-card__submeta {
    font-size: var(--b2s-fs-sm);
    color: var(--b2s-color-text-muted);
    line-height: 1.35;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .b2s-entity-row-card.is-compact .b2s-entity-row-card__meta,
  .b2s-entity-row-card.is-compact .b2s-entity-row-card__submeta {
    font-size: var(--b2s-fs-xs);
  }

  .b2s-entity-row-card__submeta {
    color: #5d6f8f;
  }

  .b2s-entity-row-card__actions {
    flex: 0 0 auto;
    display: inline-flex;
    align-items: center;
    gap: 8px;
  }

</style>
