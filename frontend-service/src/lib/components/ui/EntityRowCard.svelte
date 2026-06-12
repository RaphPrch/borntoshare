<script lang="ts">
  export let title = '';
  export let subtitle: string | null = null;
  export let tertiary: string | null = null;
  export let typeLabel: string | null = null;
  export let compact = false;
  export let className = '';
</script>

<article class={`b2s-entity-row-card ${compact ? 'is-compact' : ''} ${className}`.trim()}>
  <slot name="icon" />

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
    <slot name="actions" />
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
    border-radius: 16px;
    background: #f8fafc;
  }

  .b2s-entity-row-card.is-compact {
    padding: 10px 12px;
    border-radius: 12px;
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
    font-size: 16px;
    font-weight: 700;
    color: #101828;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .b2s-entity-row-card.is-compact .b2s-entity-row-card__title-row strong {
    font-size: 14px;
  }

  .b2s-entity-row-card__type {
    height: 22px;
    padding: 0 10px;
    border-radius: 999px;
    border: 1px solid #d8e0ef;
    background: #f4f7fc;
    color: #475467;
    font-size: 11px;
    font-weight: 700;
    display: inline-flex;
    align-items: center;
    flex: 0 0 auto;
  }

  .b2s-entity-row-card__meta,
  .b2s-entity-row-card__submeta {
    font-size: 13px;
    color: #667085;
    line-height: 1.35;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .b2s-entity-row-card.is-compact .b2s-entity-row-card__meta,
  .b2s-entity-row-card.is-compact .b2s-entity-row-card__submeta {
    font-size: 12px;
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

  @media (max-width: 760px) {
    .b2s-entity-row-card {
      align-items: flex-start;
      gap: 12px;
      padding: 14px;
    }

    .b2s-entity-row-card__title-row {
      flex-wrap: wrap;
    }
  }
</style>
