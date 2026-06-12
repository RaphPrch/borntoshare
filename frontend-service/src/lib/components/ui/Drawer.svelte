<script lang="ts">
  export let open = false;
  export let title: string | null = null;
  export let subtitle: string | null = null;
  export let width = '520px';
  export let topOffset = '0px';
  export let closeOnBackdrop = true;
  export let closeOnEscape = true;
  export let showHeader = true;
  export let showFooter = true;
  export let ariaLabelledby: string | null = null;
  export let rootClass = '';
  export let backdropClass = '';
  export let panelClass = '';
  export let contentClass = '';
  export let footerClass = '';
  export let onClose: (() => void) | null = null;

  const handleBackdrop = () => {
    if (!closeOnBackdrop) return;
    onClose?.();
  };

  const handleKeydown = (event: KeyboardEvent) => {
    if (!open || !closeOnEscape) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      onClose?.();
    }
  };
</script>

<svelte:window on:keydown={handleKeydown} />

{#if open}
  <div class={`b2s-drawer ${rootClass}`.trim()} role="presentation" style={`--b2s-drawer-width:${width};--b2s-drawer-top:${topOffset};`}>
    <button
      type="button"
      class={`b2s-drawer__backdrop ${backdropClass}`.trim()}
      aria-label="Close drawer"
      on:click={handleBackdrop}
    ></button>

    <div
      class={`b2s-drawer__panel ${panelClass}`.trim()}
      role="dialog"
      aria-modal="true"
      aria-labelledby={ariaLabelledby ?? undefined}
      aria-label={ariaLabelledby ? undefined : (title ?? 'Details')}
    >
      {#if showHeader}
        <header class="b2s-drawer__header">
          <div class="b2s-drawer__title-wrap">
            {#if title}
              <h2>{title}</h2>
            {/if}
            {#if subtitle}
              <p>{subtitle}</p>
            {/if}
          </div>
          <button type="button" class="b2s-drawer__close" aria-label="Close" on:click={() => onClose?.()}>
            <i class="bi bi-x-lg" aria-hidden="true"></i>
          </button>
        </header>
      {/if}

      <div class={`b2s-drawer__content ${contentClass}`.trim()}>
        <slot />
      </div>

      {#if showFooter}
        <footer class={`b2s-drawer__footer ${footerClass}`.trim()}>
          <slot name="footer" />
        </footer>
      {/if}
    </div>
  </div>
{/if}

<style>
  .b2s-drawer {
    position: fixed;
    inset: var(--b2s-drawer-top, 0) 0 0 0;
    z-index: 1200;
    display: flex;
    justify-content: flex-end;
  }

  .b2s-drawer__backdrop {
    position: absolute;
    inset: 0;
    border: none;
    background: rgba(2, 6, 23, 0.34);
    backdrop-filter: blur(2px);
  }

  .b2s-drawer__panel {
    position: relative;
    width: min(var(--b2s-drawer-width, 520px), 100vw);
    height: 100%;
    background: var(--b2s-color-surface, #fff);
    border-left: 1px solid var(--b2s-color-border, #dfe6f1);
    box-shadow: -24px 0 48px rgba(15, 23, 42, 0.12);
    display: grid;
    grid-template-rows: auto 1fr auto;
    animation: b2s-drawer-in 160ms ease-out;
  }

  .b2s-drawer__header {
    padding: 1rem 1rem 0.8rem;
    border-bottom: 1px solid var(--b2s-color-border, #dfe6f1);
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 0.8rem;
  }

  .b2s-drawer__title-wrap h2 {
    margin: 0;
    font-size: 1.08rem;
    font-weight: 800;
    color: var(--b2s-color-text, #0f172a);
  }

  .b2s-drawer__title-wrap p {
    margin: 0.25rem 0 0;
    color: var(--b2s-color-text-muted, #64748b);
    font-size: 0.86rem;
  }

  .b2s-drawer__close {
    width: 34px;
    height: 34px;
    border-radius: 10px;
    border: 1px solid var(--b2s-color-border, #dfe6f1);
    background: #fff;
    color: #334155;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }

  .b2s-drawer__content {
    overflow: auto;
    padding: 1rem;
  }

  .b2s-drawer__footer {
    position: sticky;
    bottom: 0;
    z-index: 2;
    border-top: 1px solid var(--b2s-color-border, #dfe6f1);
    background: var(--b2s-color-surface, #fff);
    padding: 0.75rem 1rem;
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 0.6rem;
  }

  .b2s-drawer__footer:empty {
    display: none;
  }

  @keyframes b2s-drawer-in {
    from {
      transform: translateX(18px);
      opacity: 0;
    }
    to {
      transform: translateX(0);
      opacity: 1;
    }
  }
</style>
