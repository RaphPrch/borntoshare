<script lang="ts">
  export type EntityActionVariant = 'primary' | 'secondary' | 'probe' | 'danger' | 'ghost';

  export type EntityActionItem = {
    key: string;
    label: string;
    icon?: string;
    variant?: EntityActionVariant;
    disabled?: boolean;
    title?: string;
    overflow?: boolean;
    ariaLabel?: string;
    onClick?: () => void;
  };

  export let actions: EntityActionItem[] = [];
  export let ariaLabel = 'Entity actions';
  export let align: 'start' | 'end' = 'end';

  const buttonClass = (action: EntityActionItem): string => {
    const variant = action.variant ?? 'secondary';
    if (variant === 'primary') return 'sed-btn sed-btn--primary';
    if (variant === 'probe') return 'sed-btn sed-btn--probe';
    if (variant === 'danger') return 'sed-btn sed-btn--danger';
    if (variant === 'ghost') return 'sed-btn sed-btn--ghost';
    return 'sed-btn sed-btn--secondary';
  };

  $: visibleActions = actions.filter((action) => !action.overflow);
  $: overflowActions = actions.filter((action) => action.overflow);
</script>

<div class={`b2s-action-group is-${align}`} role="toolbar" aria-label={ariaLabel}>
  {#each visibleActions as action (action.key)}
    <button
      type="button"
      class={buttonClass(action)}
      on:click={() => action.onClick?.()}
      disabled={Boolean(action.disabled)}
      title={action.title}
      aria-label={action.ariaLabel}
    >
      {#if action.icon}
        <i class={`bi ${action.icon}`} aria-hidden="true"></i>
      {/if}
      {action.label}
    </button>
  {/each}

  {#if overflowActions.length > 0}
    <details class="b2s-action-menu">
      <summary class="sed-btn sed-btn--secondary sed-btn--icon" aria-label="More actions">
        <i class="bi bi-three-dots" aria-hidden="true"></i>
      </summary>

      <div class="b2s-action-menu__content" role="menu">
        {#each overflowActions as action (action.key)}
          <button
            type="button"
            class={`b2s-action-menu__item is-${action.variant ?? 'secondary'}`}
            on:click={() => action.onClick?.()}
            disabled={Boolean(action.disabled)}
            title={action.title}
            role="menuitem"
          >
            {#if action.icon}
              <i class={`bi ${action.icon}`} aria-hidden="true"></i>
            {/if}
            {action.label}
          </button>
        {/each}
      </div>
    </details>
  {/if}
</div>

<style>
  .b2s-action-group {
    width: 100%;
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }

  .b2s-action-group.is-end {
    justify-content: flex-end;
  }

  .b2s-action-group.is-start {
    justify-content: flex-start;
  }

  .b2s-action-menu {
    position: relative;
  }

  .b2s-action-menu summary {
    list-style: none;
  }

  .b2s-action-menu summary::-webkit-details-marker {
    display: none;
  }

  .b2s-action-menu__content {
    position: absolute;
    top: calc(100% + 8px);
    right: 0;
    z-index: 30;
    min-width: 190px;
    padding: 6px;
    border: 1px solid #dde5f1;
    border-radius: 12px;
    background: #fff;
    box-shadow: 0 18px 42px rgba(15, 23, 42, 0.18);
  }

  .b2s-action-menu__item {
    width: 100%;
    min-height: 38px;
    border: none;
    border-radius: 9px;
    background: transparent;
    color: #253b5d;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 0 10px;
    font-size: 13px;
    font-weight: 700;
    text-align: left;
  }

  .b2s-action-menu__item:hover:not(:disabled) {
    background: #f4f7fb;
  }

  .b2s-action-menu__item.is-danger {
    color: #a12e2e;
  }

  .b2s-action-menu__item.is-danger:hover:not(:disabled) {
    background: #fdeaea;
  }

  .b2s-action-menu__item:disabled {
    opacity: 0.55;
    cursor: not-allowed;
  }

  @media (max-width: 900px) {
    .b2s-action-group {
      justify-content: flex-start;
    }
  }
</style>
