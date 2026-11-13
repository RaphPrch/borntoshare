<script lang="ts">
  import type { EntityActionVariant } from './EntityActionGroup.svelte';

  interface Props {
    label?: string;
    icon?: string;
    busyIcon?: string;
    busy?: boolean;
    disabled?: boolean;
    variant?: EntityActionVariant;
    iconOnly?: boolean;
    className?: string;
    title?: string | null;
    ariaLabel?: string | null;
    stopPropagation?: boolean;
    onClick?: () => void;
  }

  let {
    label = '',
    icon = '',
    busyIcon = 'bi-hourglass-split',
    busy = false,
    disabled = false,
    variant = 'secondary',
    iconOnly = false,
    className = '',
    title = null,
    ariaLabel = null,
    stopPropagation = false,
    onClick = () => {}
  }: Props = $props();

  // 'probe' is kept for existing callers and looks like a primary action
  const variantClass = (value: EntityActionVariant): string =>
    `b2s-btn-${value === 'probe' ? 'primary' : value}`;

  let resolvedIcon = $derived(busy ? busyIcon : icon);
  let classes = $derived([
    'b2s-btn',
    variantClass(variant),
    iconOnly ? 'b2s-btn-icon b2s-entity-action-button--icon' : '',
    className
  ]
    .filter(Boolean)
    .join(' '));

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
  onclick={handleClick}
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
