<script lang="ts">
  import type { EntityActionVariant } from './EntityActionGroup.svelte';

  export let label = '';
  export let icon = '';
  export let busyIcon = 'bi-hourglass-split';
  export let busy = false;
  export let disabled = false;
  export let variant: EntityActionVariant = 'secondary';
  export let iconOnly = false;
  export let className = '';
  export let title: string | null = null;
  export let ariaLabel: string | null = null;
  export let stopPropagation = false;
  export let onClick: () => void = () => {};

  // 'probe' is kept for existing callers and looks like a primary action
  const variantClass = (value: EntityActionVariant): string =>
    `b2s-btn-${value === 'probe' ? 'primary' : value}`;

  $: resolvedIcon = busy ? busyIcon : icon;
  $: classes = [
    'b2s-btn',
    variantClass(variant),
    iconOnly ? 'b2s-btn-icon b2s-entity-action-button--icon' : '',
    className
  ]
    .filter(Boolean)
    .join(' ');

  const handleClick = (event: MouseEvent) => {
    if (stopPropagation) event.stopPropagation();
    onClick();
  };
</script>

<button
  type="button"
  class={classes}
  title={title ?? ariaLabel ?? label}
  aria-label={ariaLabel ?? (iconOnly ? label : undefined)}
  aria-busy={busy}
  disabled={disabled || busy}
  on:click={handleClick}
>
  {#if resolvedIcon}
    <i class={`bi ${resolvedIcon} ${busy ? 'sed-spin' : ''}`} aria-hidden="true"></i>
  {/if}
  {#if !iconOnly}
    <span>{label}</span>
  {/if}
</button>

<style>
  .b2s-entity-action-button--icon {
    width: 34px;
    min-width: 34px;
    height: 34px;
    padding: 0;
    justify-content: center;
  }
</style>
