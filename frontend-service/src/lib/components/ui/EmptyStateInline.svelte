<script lang="ts">
  
  
  interface Props {
    message: string;
    className?: string;
    /** What to do from here: a link (href) or an action (onAction), shown under the sentence */
    actionLabel?: string | null;
    href?: string | null;
    onAction?: (() => void) | null;
    actionIcon?: string | null;
    /** Keyboard shortcut of the same action, shown next to it (« N ») */
    shortcut?: string | null;
  }

  let {
    message,
    className = '',
    actionLabel = null,
    href = null,
    onAction = null,
    actionIcon = null,
    shortcut = null
  }: Props = $props();
</script>

<div class={`b2s-empty-inline ${className}`.trim()}>
  <span>{message}</span>
  {#if actionLabel && (href || onAction)}
    {#if href}
      <a class="b2s-btn b2s-btn-secondary b2s-btn-sm b2s-empty-inline__action" {href}>{#if actionIcon}<i class={`bi ${actionIcon}`} aria-hidden="true"></i>{/if}{actionLabel}{#if shortcut}<kbd>{shortcut}</kbd>{/if}</a>
    {:else}
      <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm b2s-empty-inline__action" onclick={() => onAction?.()}>{#if actionIcon}<i class={`bi ${actionIcon}`} aria-hidden="true"></i>{/if}{actionLabel}{#if shortcut}<kbd>{shortcut}</kbd>{/if}</button>
    {/if}
  {/if}
</div>

<style>
  /* A list or a panel with nothing to show: the same short sentence, centered, everywhere; and what to do next */
  .b2s-empty-inline {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 10px;
    padding: 20px 12px;
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-text-sm);
    text-align: center;
  }
  .b2s-empty-inline__action { display: inline-flex; align-items: center; gap: 6px; }
  .b2s-empty-inline__action kbd { font-family: var(--b2s-font-mono); font-size: 10px; padding: 0 5px; border: 1px solid var(--b2s-color-border); border-radius: 4px; color: var(--b2s-color-text-muted); }
</style>
