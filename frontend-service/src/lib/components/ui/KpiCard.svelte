<script lang="ts">
  /** Summary figure shown at the top of a page: icon, label, value and an optional hint or link. */
  export let label: string;
  export let value: string | number;
  export let icon: string;
  export let tone: 'info' | 'success' | 'warning' | 'danger' | 'purple' | 'neutral' = 'info';
  export let hint: string | null = null;
  export let href: string | null = null;

  // Numbers keep the large size; a text value (« 27 min ago », « Never ») is set smaller
  $: isText = typeof value === 'string' && !/^[\d\s.,%+-]*$/.test(value);
</script>

<svelte:element this={href ? 'a' : 'article'} {href} class="b2s-kpi" class:is-link={Boolean(href)}>
  <span class={`b2s-kpi__icon is-${tone}`} aria-hidden="true"><i class={`bi ${icon}`}></i></span>
  <span class="b2s-kpi__body">
    <span class="b2s-kpi__label">{label}</span>
    <strong class="b2s-kpi__value" class:is-text={isText} title={isText ? String(value) : undefined}>{value}</strong>
    {#if hint}<span class="b2s-kpi__hint">{hint}</span>{/if}
  </span>
</svelte:element>

<style>
  .b2s-kpi {
    display: flex;
    align-items: center;
    gap: 16px;
    min-height: 96px;
    padding: 16px 20px;
    border: 1px solid var(--b2s-color-border-soft);
    border-radius: var(--b2s-radius-md);
    background: var(--b2s-color-surface);
    color: var(--b2s-color-text);
    text-decoration: none;
    box-shadow: 0 3px 10px rgba(18, 31, 64, 0.04);
  }

  .b2s-kpi.is-link:hover {
    border-color: #c9d6ea;
    box-shadow: 0 6px 18px rgba(18, 31, 64, 0.08);
  }

  .b2s-kpi__icon {
    width: 44px;
    height: 44px;
    flex: 0 0 auto;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: var(--b2s-radius-md);
    font-size: var(--b2s-fs-xl);
  }

  .b2s-kpi__icon.is-info { background: #eaf2ff; color: var(--b2s-color-info-strong); }
  .b2s-kpi__icon.is-success { background: #e8f8ef; color: var(--b2s-color-success-strong); }
  .b2s-kpi__icon.is-warning { background: #fff4e5; color: var(--b2s-color-warning-strong); }
  .b2s-kpi__icon.is-danger { background: #fdecec; color: var(--b2s-color-danger-strong); }
  .b2s-kpi__icon.is-purple { background: #f1ecff; color: #6d28d9; }
  .b2s-kpi__icon.is-neutral { background: var(--b2s-color-neutral-soft); color: var(--b2s-color-text-soft); }

  .b2s-kpi__body {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .b2s-kpi__label {
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-sm);
    font-weight: 500;
  }

  .b2s-kpi__value {
    font-size: var(--b2s-fs-page-title);
    font-weight: 700;
    line-height: 1.15;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  /* A text value (« 27 min ago ») is smaller than a number, so that it fits on one line */
  .b2s-kpi__value.is-text {
    font-size: var(--b2s-fs-xl);
    line-height: 1.4;
  }

  .b2s-kpi__hint {
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-xs);
  }
</style>
