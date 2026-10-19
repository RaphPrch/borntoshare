<script lang="ts">
  /**
   * Side panel opening from the right (single drawer component of the app).
   * Header: icon + title + subtitle + close button; pass showHeader={false} for a custom header.
   * Slots: default (body), "header-icon", "footer".
   */
  export let open = false;
  export let title: string | null = null;
  export let subtitle: string | null = null;
  export let iconClass: string | null = null;
  export let width = '560px';
  export let topOffset = '70px';
  export let closeOnBackdrop = true;
  export let closeOnEscape = true;
  export let showHeader = true;
  export let showFooter = true;
  export let ariaLabelledby = 'b2s-drawer-title';
  export let rootClass = '';
  export let backdropClass = '';
  export let panelClass = '';
  export let contentClass = '';
  export let bodyClass = '';
  export let footerClass = '';
  export let onClose: (() => void) | null = null;

  const handleKeydown = (event: KeyboardEvent) => {
    if (!open || !closeOnEscape || event.key !== 'Escape') return;
    event.preventDefault();
    onClose?.();
  };
</script>

<svelte:window on:keydown={handleKeydown} />

{#if open}
  <div
    class={`b2s-drawer b2s-entity-drawer ${rootClass}`.trim()}
    role="presentation"
    style={`--b2s-drawer-width:${width};--b2s-drawer-top:${topOffset};`}
  >
    <button
      type="button"
      class={`b2s-drawer__backdrop ${backdropClass}`.trim()}
      aria-label="Close drawer"
      on:click={() => closeOnBackdrop && onClose?.()}
    ></button>

    <div
      class={`b2s-drawer__panel ${panelClass}`.trim()}
      role="dialog"
      aria-modal="true"
      aria-labelledby={showHeader ? ariaLabelledby : undefined}
      aria-label={showHeader ? undefined : (title ?? 'Details')}
    >
      <div class={`b2s-drawer__content ${contentClass}`.trim()}>
        {#if showHeader}
          <section class="b2s-entity-drawer__layout">
            <header class="b2s-entity-drawer__header">
              <div class="b2s-entity-drawer__title-row">
                <slot name="header-icon">
                  {#if iconClass}
                    <span class="b2s-entity-drawer__icon" aria-hidden="true">
                      <i class={iconClass}></i>
                    </span>
                  {/if}
                </slot>
                <div class="b2s-entity-drawer__header-copy">
                  <h2 id={ariaLabelledby}>{title ?? ''}</h2>
                  {#if subtitle}
                    <p>{subtitle}</p>
                  {/if}
                </div>
              </div>
              <button type="button" class="b2s-entity-drawer__close" aria-label="Close drawer" on:click={() => onClose?.()}>
                <i class="bi bi-x-lg" aria-hidden="true"></i>
              </button>
            </header>
            <div class={`b2s-entity-drawer__body ${bodyClass}`.trim()}>
              <slot />
            </div>
          </section>
        {:else}
          <slot />
        {/if}
      </div>

      {#if showFooter}
        <footer class={`b2s-drawer__footer b2s-entity-drawer__footer ${footerClass}`.trim()}>
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
    z-index: 1240;
    display: flex;
    justify-content: flex-end;
  }

  .b2s-drawer__backdrop {
    position: absolute;
    inset: 0;
    border: none;
    background: rgba(15, 23, 42, 0.22);
  }

  .b2s-drawer__panel {
    position: relative;
    height: 100%;
    background: var(--b2s-color-surface, #fff);
    display: grid;
    grid-template-rows: 1fr auto;
    animation: b2s-drawer-in 160ms ease-out;
  }

  .b2s-drawer__footer {
    position: sticky;
    bottom: 0;
    z-index: 2;
    background: var(--b2s-color-surface, #fff);
    display: flex;
    align-items: center;
    justify-content: flex-end;
  }

  .b2s-drawer__footer:empty {
    display: none;
  }

    .b2s-drawer__backdrop {
    background: rgba(15, 23, 42, 0.22);
    backdrop-filter: none;
  }

  .b2s-drawer__panel {
    width: min(var(--b2s-drawer-width, 560px), 100vw);
    max-width: min(var(--b2s-drawer-width, 560px), 100vw);
    min-width: min(100vw, 460px);
    border-left: 1px solid #e5eaf3;
    border-radius: 0;
    box-shadow: -20px 0 42px rgba(15, 23, 42, 0.16);
    overflow: hidden;
  }

  .b2s-drawer__content {
    padding: 0;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    min-height: 0;
  }

  .b2s-drawer__footer {
    padding: 16px 24px;
    border-top: 1px solid #e8edf6;
    gap: 12px;
  }

  .b2s-entity-drawer__layout {
    display: flex;
    flex-direction: column;
    min-height: 0;
    height: 100%;
    background: #fff;
  }

  .b2s-entity-drawer__header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
    padding: 22px 24px 18px;
    border-bottom: 1px solid #e8edf6;
    background: #fff;
  }

  .b2s-entity-drawer__title-row {
    min-width: 0;
    display: flex;
    align-items: flex-start;
    gap: 12px;
  }

  .b2s-entity-drawer__icon {
    width: 40px;
    height: 40px;
    border-radius: 12px;
    border: 1px solid #d7e1f0;
    background: #edf4ff;
    color: var(--b2s-topbar-bg, #0b1530);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex: 0 0 auto;
  }

  .b2s-entity-drawer__header-copy {
    min-width: 0;
  }

  .b2s-entity-drawer__header-copy h2 {
    margin: 0;
    font-size: 20px;
    line-height: 1.2;
    font-weight: 700;
    color: #0f172a;
  }

  .b2s-entity-drawer__header-copy p {
    margin: 6px 0 0;
    font-size: 14px;
    color: #667085;
  }

  .b2s-entity-drawer__close {
    width: 36px;
    height: 36px;
    border: none;
    border-radius: 10px;
    background: transparent;
    color: #667085;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex: 0 0 auto;
  }

  .b2s-entity-drawer__close:hover {
    background: #f2f5fb;
    color: #1f2a44;
  }

  .b2s-entity-drawer__body {
    flex: 1;
    min-height: 0;
    overflow: auto;
    padding: 20px 24px 24px;
  }

  @media (max-width: 760px) {
    .b2s-drawer__panel {
      width: 100vw;
      max-width: 100vw;
      min-width: 100vw;
    }

    .b2s-entity-drawer__header,
    .b2s-entity-drawer__body {
      padding-inline: 18px;
    }
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
