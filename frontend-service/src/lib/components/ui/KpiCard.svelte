<script lang="ts">
  import { type StatusVariant } from '$lib/constants/status';

  export let label = '';
  export let value: string | number = '—';
  export let icon: string | null = null;
  export let hint: string | null = null;
  export let variant: StatusVariant | null = null;
</script>

<article class={`b2s-kpi-card ${variant ? `is-${variant}` : ''}`}>
  <div class="b2s-kpi-card__head">
    <span class="b2s-kpi-card__label">{label}</span>
    {#if icon}
      <i class={`bi ${icon}`} aria-hidden="true"></i>
    {/if}
  </div>
  <div class="b2s-kpi-card__value">{value}</div>
  {#if hint}
    <p class="b2s-kpi-card__hint">{hint}</p>
  {/if}
</article>

<style>
  .b2s-kpi-card {
    border-radius: var(--b2s-radius-md, 16px);
    border: 1px solid var(--b2s-color-border, #dfe6f1);
    background: var(--b2s-color-surface, #fff);
    box-shadow: var(--b2s-shadow-sm, 0 2px 8px rgba(15, 23, 42, 0.06));
    padding: 0.9rem 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    min-height: 96px;
  }

  .b2s-kpi-card__head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.6rem;
    color: var(--b2s-color-text-muted, #64748b);
    font-size: 0.8rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .b2s-kpi-card__value {
    font-size: clamp(1.2rem, 1.6vw, 1.7rem);
    font-weight: 800;
    color: var(--b2s-color-text, #0f172a);
    line-height: 1.1;
  }

  .b2s-kpi-card__hint {
    margin: 0;
    color: var(--b2s-color-text-muted, #64748b);
    font-size: 0.82rem;
  }

  .b2s-kpi-card.is-success {
    border-color: rgba(22, 101, 52, 0.2);
    background: #f6fdf8;
  }

  .b2s-kpi-card.is-warning {
    border-color: rgba(146, 64, 14, 0.2);
    background: #fffaf2;
  }

  .b2s-kpi-card.is-error {
    border-color: rgba(153, 27, 27, 0.2);
    background: #fff7f7;
  }

  .b2s-kpi-card.is-info {
    border-color: rgba(37, 99, 235, 0.2);
    background: #f8faff;
  }
</style>

