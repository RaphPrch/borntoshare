<script lang="ts">
  import { onMount } from 'svelte';
  import { t } from '$lib/i18n';

  /**
   * Page layout shared by zones, storage endpoints and storage roots:
   * list pane on the left (resizable), selected entity on the right. No title band: the top menu says where
   * we are and the entity header carries the page title. `title` names the page for screen readers.
   * Slots: "list" (EntitySidebarTree), default (entity detail).
   */
  export let title: string;

  const WIDTH_KEY = 'b2s.workspace.listWidth';
  const DEFAULT_WIDTH = 340;
  const MIN_WIDTH = 260;
  const MAX_WIDTH = 560;

  let listWidth = DEFAULT_WIDTH;
  let dragStart: { x: number; width: number } | null = null;

  const clamp = (value: number): number => Math.round(Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, value)));

  onMount(() => {
    try {
      const stored = Number(localStorage.getItem(WIDTH_KEY));
      if (stored) listWidth = clamp(stored);
    } catch {
      // Storage unavailable: default width
    }
  });

  function saveWidth(width: number): void {
    listWidth = clamp(width);
    try {
      localStorage.setItem(WIDTH_KEY, String(listWidth));
    } catch {
      // Not remembered
    }
  }

  function startDrag(event: PointerEvent): void {
    dragStart = { x: event.clientX, width: listWidth };
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
  }

  function drag(event: PointerEvent): void {
    if (dragStart) listWidth = clamp(dragStart.width + event.clientX - dragStart.x);
  }

  function endDrag(): void {
    if (!dragStart) return;
    dragStart = null;
    saveWidth(listWidth);
  }

  function resizeWithKeys(event: KeyboardEvent): void {
    const step = { ArrowLeft: -16, ArrowRight: 16 }[event.key];
    if (!step) return;
    event.preventDefault();
    saveWidth(listWidth + step);
  }
</script>

<div class="b2s-workspace-page" role="region" aria-label={title}>
  <div class="b2s-workspace" class:has-list={$$slots.list} class:is-resizing={Boolean(dragStart)} style={`--b2s-list-width:${listWidth}px`}>
    {#if $$slots.list}
      <div class="b2s-workspace__list">
        <slot name="list" />
        <!-- svelte-ignore a11y-no-noninteractive-tabindex a11y-no-noninteractive-element-interactions -->
        <div
          class="b2s-workspace__resizer"
          role="separator"
          aria-orientation="vertical"
          aria-label={t('Resize the list')}
          aria-valuenow={listWidth}
          aria-valuemin={MIN_WIDTH}
          aria-valuemax={MAX_WIDTH}
          tabindex="0"
          title={t('Drag to resize · double-click to reset')}
          on:pointerdown={startDrag}
          on:pointermove={drag}
          on:pointerup={endDrag}
          on:pointercancel={endDrag}
          on:dblclick={() => saveWidth(DEFAULT_WIDTH)}
          on:keydown={resizeWithKeys}
        ></div>
      </div>
    {/if}
    <section class="b2s-workspace__detail">
      <slot />
    </section>
  </div>
</div>

<style>
  .b2s-workspace-page {
    display: grid;
    gap: 20px;
    padding: var(--b2s-page-padding);
  }

  .b2s-workspace {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 24px;
    align-items: start;
  }

  .b2s-workspace.has-list {
    grid-template-columns: var(--b2s-list-width, 340px) minmax(0, 1fr);
  }

  .b2s-workspace.is-resizing {
    cursor: col-resize;
    user-select: none;
  }

  /* Full column height so the sticky list pane follows the scroll */
  .b2s-workspace__list {
    position: relative;
    align-self: stretch;
    min-width: 0;
  }

  .b2s-workspace__resizer {
    position: absolute;
    top: 0;
    right: -16px;
    bottom: 0;
    width: 8px;
    border-radius: 4px;
    cursor: col-resize;
    touch-action: none;
  }

  .b2s-workspace__resizer::after {
    content: '';
    position: sticky;
    top: 50vh;
    display: block;
    width: 4px;
    height: 40px;
    margin: 0 auto;
    border-radius: 4px;
    background: transparent;
    transition: background 0.15s;
  }

  .b2s-workspace__resizer:hover::after,
  .b2s-workspace__resizer:focus-visible::after,
  .is-resizing .b2s-workspace__resizer::after {
    background: var(--b2s-color-border-mid);
  }

  .b2s-workspace__resizer:focus-visible {
    outline: none;
  }

  .b2s-workspace__detail {
    min-width: 0;
    display: grid;
    gap: 20px;
    align-content: start;
  }

  @media (max-width: 1100px) {
    .b2s-workspace.has-list {
      grid-template-columns: minmax(0, 1fr);
    }

    .b2s-workspace__resizer {
      display: none;
    }
  }
</style>
