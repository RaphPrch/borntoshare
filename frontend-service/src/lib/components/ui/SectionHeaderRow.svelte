<script lang="ts">
  export let title = '';
  export let subtitle: string | null = null;
  export let helper: string | null = null;
  export let count: number | null = null;
  export let compact = false;
  export let rowClass = '';
</script>

<div class={`b2s-section-header-row ${compact ? 'is-compact' : ''} ${rowClass}`.trim()}>
  <div class="b2s-section-header-row__copy">
    <h3>
      {title}
      {#if typeof count === 'number'}
        <span>({count})</span>
      {/if}
    </h3>

    {#if subtitle}
      <p>{subtitle}</p>
    {/if}

    {#if helper}
      <small>{helper}</small>
    {/if}
  </div>

  <div class="b2s-section-header-row__actions">
    <slot name="actions" />
  </div>
</div>

<style>
  .b2s-section-header-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    width: 100%;
  }

  .b2s-section-header-row.is-compact {
    min-height: 40px;
  }

  .b2s-section-header-row__copy {
    min-width: 0;
    display: grid;
    gap: 4px;
  }

  .b2s-section-header-row__copy h3 {
    margin: 0;
    display: inline-flex;
    align-items: baseline;
    gap: 8px;
    font-size: 16px;
    line-height: 1.25;
    font-weight: 700;
    color: #101828;
  }

  .b2s-section-header-row__copy h3 span {
    font-size: 13px;
    color: #667085;
    font-weight: 600;
  }

  .b2s-section-header-row__copy p,
  .b2s-section-header-row__copy small {
    margin: 0;
    font-size: 13px;
    line-height: 1.4;
    color: #667085;
  }

  .b2s-section-header-row__actions {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    flex: 0 0 auto;
  }

  @media (max-width: 760px) {
    .b2s-section-header-row {
      align-items: flex-start;
      flex-direction: column;
    }

    .b2s-section-header-row__actions {
      width: 100%;
    }
  }
</style>

