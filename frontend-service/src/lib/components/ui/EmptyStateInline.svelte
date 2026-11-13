<script lang="ts">
  export let message: string;
  export let className = '';
  /** What to do from here: a link (href) or an action (onAction), shown under the sentence */
  export let actionLabel: string | null = null;
  export let href: string | null = null;
  export let onAction: (() => void) | null = null;
  export let actionIcon: string | null = null;
  /** Keyboard shortcut of the same action, shown next to it (« N ») */
  export let shortcut: string | null = null;
</script>

<div class={`b2s-empty-inline ${className}`.trim()}>
  <span>{message}</span>
  {#if actionLabel && (href || onAction)}
    {#if href}
      <a class="b2s-btn b2s-btn-secondary b2s-btn-sm b2s-empty-inline__action" {href}>{#if actionIcon}<i class={`bi ${actionIcon}`} aria-hidden="true"></i>{/if}{actionLabel}{#if shortcut}<kbd>{shortcut}</kbd>{/if}</a>
    {:else}
      <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm b2s-empty-inline__action" on:click={() => onAction?.()}>{#if actionIcon}<i class={`bi ${actionIcon}`} aria-hidden="true"></i>{/if}{actionLabel}{#if shortcut}<kbd>{shortcut}</kbd>{/if}</button>
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
