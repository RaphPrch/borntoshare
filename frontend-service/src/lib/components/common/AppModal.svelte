<script lang="ts">
  import { fade, fly } from 'svelte/transition';
  import { onDestroy, tick } from 'svelte';

  export let open = false;
  export let onClose: () => void;

  export let backdropClass = 'b2s-modal-backdrop';
  export let modalClass = 'b2s-modal';
  export let contentClass = 'b2s-modal-content';
  export let ariaLabelledby: string | null = null;
  export let role: 'dialog' | 'alertdialog' = 'dialog';
  export let closeLabel = 'Close';
  export let showClose = true;
  export let closeClass = 'b2s-modal-close';
  export let closeOnBackdrop = true;
  export let closeOnEscape = true;
  export let trapFocus = true;
  export let restoreFocusOnClose = true;
  export let stopPropagation = true;
  export let useFly = true;
  export let useFade = true;
  export let flyConfig: { y?: number; duration?: number } = { y: 24, duration: 180 };
  export let wrapContent = true;

  let modalEl: HTMLDivElement | null = null;
  let wasOpen = false;
  let lastFocusedElement: HTMLElement | null = null;

  const FOCUSABLE_SELECTOR = [
    'a[href]',
    'area[href]',
    'input:not([disabled]):not([type="hidden"])',
    'select:not([disabled])',
    'textarea:not([disabled])',
    'button:not([disabled])',
    '[tabindex]:not([tabindex="-1"])',
    '[contenteditable="true"]'
  ].join(',');

  function getFocusableElements(container: HTMLElement): HTMLElement[] {
    return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter((el) => {
      const hiddenByAria = el.getAttribute('aria-hidden') === 'true';
      const visible = el.getClientRects().length > 0;
      return !hiddenByAria && visible;
    });
  }

  async function focusFirstElementInModal() {
    await tick();
    if (!open || !modalEl) return;

    const focusable = getFocusableElements(modalEl);
    (focusable[0] ?? modalEl).focus();
  }

  function restorePreviousFocus() {
    if (!restoreFocusOnClose) {
      lastFocusedElement = null;
      return;
    }

    if (lastFocusedElement && typeof lastFocusedElement.focus === 'function') {
      lastFocusedElement.focus();
    }
    lastFocusedElement = null;
  }

  $: if (open && !wasOpen) {
    wasOpen = true;
    lastFocusedElement = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    focusFirstElementInModal();
  }

  $: if (!open && wasOpen) {
    wasOpen = false;
    restorePreviousFocus();
  }

  onDestroy(() => {
    if (wasOpen) restorePreviousFocus();
  });

  function handleBackdropClick() {
    if (closeOnBackdrop) onClose?.();
  }

  function handleKeydown(e: KeyboardEvent) {
    if (closeOnEscape && e.key === 'Escape') {
      e.preventDefault();
      if (stopPropagation) e.stopPropagation();
      onClose?.();
      return;
    }

    if (trapFocus && e.key === 'Tab' && modalEl) {
      const focusable = getFocusableElements(modalEl);
      if (focusable.length === 0) {
        e.preventDefault();
        modalEl.focus();
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      const isInModal = active ? modalEl.contains(active) : false;

      if (e.shiftKey) {
        if (!isInModal || active === first) {
          e.preventDefault();
          last.focus();
        }
      } else {
        if (!isInModal || active === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }

    if (stopPropagation) e.stopPropagation();
  }

  function handleModalClick(e: MouseEvent) {
    if (stopPropagation) e.stopPropagation();
  }
</script>

{#if open}
  <div
    class={backdropClass}
    role="presentation"
    on:click={handleBackdropClick}
  >
    {#if useFly}
      {#if useFade}
        <div
          class={modalClass}
          bind:this={modalEl}
          in:fly={flyConfig}
          out:fade
          role={role}
          aria-modal="true"
          aria-labelledby={ariaLabelledby}
          tabindex="-1"
          on:click={handleModalClick}
          on:keydown={handleKeydown}
        >
          {#if showClose}
            <button class={closeClass} aria-label={closeLabel} on:click={onClose}>×</button>
          {/if}

          {#if wrapContent}
            <div class={contentClass}>
              <slot />
            </div>
          {:else}
            <slot />
          {/if}
        </div>
      {:else}
        <div
          class={modalClass}
          bind:this={modalEl}
          in:fly={flyConfig}
          role={role}
          aria-modal="true"
          aria-labelledby={ariaLabelledby}
          tabindex="-1"
          on:click={handleModalClick}
          on:keydown={handleKeydown}
        >
          {#if showClose}
            <button class={closeClass} aria-label={closeLabel} on:click={onClose}>×</button>
          {/if}

          {#if wrapContent}
            <div class={contentClass}>
              <slot />
            </div>
          {:else}
            <slot />
          {/if}
        </div>
      {/if}
    {:else}
      <div
        class={modalClass}
        bind:this={modalEl}
        role={role}
        aria-modal="true"
        aria-labelledby={ariaLabelledby}
        tabindex="-1"
        on:click={handleModalClick}
        on:keydown={handleKeydown}
      >
        {#if showClose}
          <button class={closeClass} aria-label={closeLabel} on:click={onClose}>×</button>
        {/if}

        {#if wrapContent}
          <div class={contentClass}>
            <slot />
          </div>
        {:else}
          <slot />
        {/if}
      </div>
    {/if}
  </div>
{/if}
