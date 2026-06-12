<script lang="ts">
  import Drawer from '$lib/components/ui/Drawer.svelte';

  export let open = false;
  export let title = 'Details';
  export let subtitle: string | null = null;
  export let iconClass: string | null = null;
  export let onClose: () => void = () => {};
  export let ariaLabelledby = 'entity-drawer-title';
  export let width = '560px';
  export let topOffset = '70px';
  export let rootClass = '';
  export let bodyClass = '';
  export let footerClass = '';
  export let showFooter = true;
</script>

<Drawer
  {open}
  onClose={onClose}
  {topOffset}
  {width}
  showHeader={false}
  {showFooter}
  ariaLabelledby={ariaLabelledby}
  rootClass={`b2s-entity-drawer ${rootClass}`.trim()}
  backdropClass="b2s-entity-drawer__overlay"
  panelClass="b2s-entity-drawer__panel"
  contentClass="b2s-entity-drawer__content"
  footerClass={`b2s-entity-drawer__footer ${footerClass}`.trim()}
>
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
          <h2 id={ariaLabelledby}>{title}</h2>
          {#if subtitle}
            <p>{subtitle}</p>
          {/if}
        </div>
      </div>

      <button
        type="button"
        class="b2s-entity-drawer__close"
        aria-label="Close drawer"
        on:click={onClose}
      >
        <i class="bi bi-x-lg" aria-hidden="true"></i>
      </button>
    </header>

    <div class={`b2s-entity-drawer__body ${bodyClass}`.trim()}>
      <slot />
    </div>
  </section>

  <svelte:fragment slot="footer">
    <slot name="footer" />
  </svelte:fragment>
</Drawer>

<style>
  :global(.b2s-entity-drawer) {
    z-index: 1240;
  }

  :global(.b2s-entity-drawer__overlay) {
    background: rgba(15, 23, 42, 0.22);
    backdrop-filter: none;
  }

  :global(.b2s-entity-drawer__panel) {
    width: min(var(--b2s-drawer-width, 560px), 100vw);
    max-width: min(var(--b2s-drawer-width, 560px), 100vw);
    min-width: min(100vw, 460px);
    border-left: 1px solid #e5eaf3;
    border-radius: 0;
    box-shadow: -20px 0 42px rgba(15, 23, 42, 0.16);
    overflow: hidden;
  }

  :global(.b2s-entity-drawer__content) {
    padding: 0;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    min-height: 0;
  }

  :global(.b2s-entity-drawer__footer) {
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
    :global(.b2s-entity-drawer__panel) {
      width: 100vw;
      max-width: 100vw;
      min-width: 100vw;
    }

    .b2s-entity-drawer__header,
    .b2s-entity-drawer__body {
      padding-inline: 18px;
    }
  }
</style>
