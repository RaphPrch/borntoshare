<script lang="ts">
  import { t } from '$lib/i18n';

  /** Selectable option card used by wizards (type choice). Disabled options say why with a badge. */
  export let icon: string;
  export let title: string;
  export let description: string | null = null;
  export let selected = false;
  export let disabled = false;
  export let badge: string | null = null;
  /** Show a chevron: the card moves to the next step on click */
  export let navigates = false;
  export let onSelect: () => void = () => {};
</script>

<button
  type="button"
  class="b2s-choice"
  class:is-selected={selected}
  aria-pressed={navigates ? undefined : selected}
  {disabled}
  on:click={onSelect}
>
  <span class="b2s-choice__icon" aria-hidden="true"><i class={`bi ${icon}`}></i></span>
  <span class="b2s-choice__copy">
    <span class="b2s-choice__title">
      {title}
      {#if disabled}
        <span class="b2s-choice__badge">{badge ?? t('Coming soon')}</span>
      {:else if badge}
        <span class="b2s-choice__badge is-info">{badge}</span>
      {/if}
    </span>
    {#if description}<span class="b2s-choice__desc">{description}</span>{/if}
  </span>
  {#if navigates && !disabled}
    <i class="bi bi-chevron-right b2s-choice__chevron" aria-hidden="true"></i>
  {:else if selected}
    <i class="bi bi-check-circle-fill b2s-choice__check" aria-hidden="true"></i>
  {/if}
</button>

<style>
  .b2s-choice {
    width: 100%;
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 16px;
    border: 1px solid #e5eaf3;
    border-radius: var(--b2s-radius-md);
    background: var(--b2s-color-surface);
    color: var(--b2s-color-text);
    text-align: left;
    cursor: pointer;
    transition: border-color 120ms ease, background-color 120ms ease;
  }

  .b2s-choice:hover:not(:disabled) {
    border-color: #c9d6ea;
    background: #f8fbff;
  }

  .b2s-choice.is-selected {
    border-color: var(--b2s-topbar-bg);
    background: #f5f8ff;
    box-shadow: 0 0 0 1px var(--b2s-topbar-bg);
  }

  .b2s-choice:focus-visible {
    outline: none;
    box-shadow: var(--b2s-focus-ring);
  }

  .b2s-choice:disabled {
    cursor: not-allowed;
    background: #fafbfc;
  }

  .b2s-choice:disabled .b2s-choice__icon,
  .b2s-choice:disabled .b2s-choice__desc,
  .b2s-choice:disabled .b2s-choice__title {
    opacity: 0.6;
  }

  .b2s-choice__icon {
    width: 44px;
    height: 44px;
    flex: 0 0 auto;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: var(--b2s-radius-md);
    background: #edf4ff;
    color: var(--b2s-topbar-bg);
    font-size: var(--b2s-fs-xl);
  }

  .b2s-choice__copy {
    flex: 1 1 auto;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .b2s-choice__title {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
    font-size: var(--b2s-fs-md);
    font-weight: 600;
  }

  .b2s-choice__desc {
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-sm);
    line-height: 1.4;
  }

  .b2s-choice__badge {
    padding: 1px 8px;
    border-radius: var(--b2s-radius-pill);
    background: #f1f5f9;
    color: #475569;
    font-size: var(--b2s-fs-xs);
    font-weight: 500;
  }

  .b2s-choice__badge.is-info {
    background: #eaf2ff;
    color: #1d4ed8;
  }

  .b2s-choice__chevron,
  .b2s-choice__check {
    flex: 0 0 auto;
    color: var(--b2s-color-text-muted);
  }

  .b2s-choice__check {
    color: var(--b2s-topbar-bg);
    font-size: var(--b2s-fs-lg);
  }

  /* opt-in grid for a list of cards */
  :global(.b2s-choice-grid) {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 12px;
  }
</style>
