<script lang="ts">
  export let iconClass: string | null = null;
  export let title = 'No data available';
  export let description: string | null = null;
  export let actionLabel: string | null = null;
  export let onAction: (() => void) | null = null;
</script>

<div class="b2s-empty-state-v2">
  {#if iconClass}
    <div class="b2s-empty-state-v2__icon" aria-hidden="true">
      <i class={iconClass}></i>
    </div>
  {/if}

  <h3>{title}</h3>

  {#if description}
    <p>{description}</p>
  {/if}

  {#if actionLabel && onAction}
    <button type="button" class="b2s-empty-state-v2__action" on:click={onAction}>
      {actionLabel}
    </button>
  {/if}
</div>

<style>
  .b2s-empty-state-v2 {
    border: 1px dashed rgba(148, 163, 184, 0.5);
    border-radius: var(--b2s-radius-md, 16px);
    background: rgba(248, 250, 252, 0.65);
    padding: 1.4rem 1rem;
    text-align: center;
    color: var(--b2s-color-text-muted, #64748b);
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.55rem;
  }

  .b2s-empty-state-v2__icon {
    width: 42px;
    height: 42px;
    border-radius: 999px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: rgba(59, 130, 246, 0.1);
    color: #1d4ed8;
  }

  .b2s-empty-state-v2 h3 {
    margin: 0;
    color: var(--b2s-color-text, #0f172a);
    font-size: 1rem;
    font-weight: 700;
  }

  .b2s-empty-state-v2 p {
    margin: 0;
    max-width: 60ch;
    font-size: 0.9rem;
  }

  .b2s-empty-state-v2__action {
    border-radius: 10px;
    border: 1px solid rgba(37, 99, 235, 0.24);
    background: #eef2ff;
    color: #1d4ed8;
    padding: 0.45rem 0.75rem;
    font-weight: 700;
  }
</style>

