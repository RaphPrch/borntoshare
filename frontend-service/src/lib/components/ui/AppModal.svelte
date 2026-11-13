<script lang="ts">

  import { t } from '$lib/i18n';
  import { fade } from 'svelte/transition';
  import { dur, MOTION, pop } from '$lib/utils/motion';
  import { onDestroy, tick } from 'svelte';
  import { browser } from '$app/environment';


  
  
  interface Props {
    open?: boolean;
    onClose: () => void;
    backdropClass?: string;
    modalClass?: string;
    contentClass?: string;
    ariaLabelledby?: string | null;
    role?: 'dialog' | 'alertdialog';
    closeLabel?: any;
    showClose?: boolean;
    closeClass?: string;
    closeOnBackdrop?: boolean;
    closeOnEscape?: boolean;
    trapFocus?: boolean;
    restoreFocusOnClose?: boolean;
    stopPropagation?: boolean;
    useFly?: boolean;
    useFade?: boolean;
    flyConfig?: { y?: number; duration?: number };
    wrapContent?: boolean;
    /** md = 560px (confirmations), lg = 760px (forms), xl = 1180px (browsers, multi-column forms) */
    size?: 'md' | 'lg' | 'xl' | null;
    /** Standard header (icon + title + subtitle + close); omit title to render a custom header */
    title?: string | null;
    subtitle?: string | null;
    iconClass?: string | null;
    children?: import('svelte').Snippet;
    footer?: import('svelte').Snippet;
    footerStart?: import('svelte').Snippet;
  }

  let {
    open = false,
    onClose,
    backdropClass = 'b2s-modal-backdrop',
    modalClass = 'b2s-modal',
    contentClass = 'b2s-modal-content',
    ariaLabelledby = null,
    role = 'dialog',
    closeLabel = t('Close'),
    showClose = true,
    closeClass = 'b2s-modal-close',
    closeOnBackdrop = true,
    closeOnEscape = true,
    trapFocus = true,
    restoreFocusOnClose = true,
    stopPropagation = true,
    useFly = true,
    useFade = true,
    flyConfig = { y: 12, duration: 220 },
    wrapContent = true,
    size = null,
    title = null,
    subtitle = null,
    iconClass = null,
    children,
    footer,
    footerStart
  }: Props = $props();

  let modalEl: HTMLDivElement | null = $state(null);
  let wasOpen = $state(false);
  let lastFocusedElement: HTMLElement | null = $state(null);

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

  // Focus handling only exists in the browser (a modal can be open at SSR, e.g. ?create=1)
  $effect.pre(() => {
    if (browser && open && !wasOpen) {
      wasOpen = true;
      lastFocusedElement = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      focusFirstElementInModal();
    }
  });

  $effect.pre(() => {
    if (!open && wasOpen) {
      wasOpen = false;
      restorePreviousFocus();
    }
  });

  onDestroy(() => {
    if (wasOpen) restorePreviousFocus();
  });

  // Render at the end of <body>: a transformed ancestor would otherwise become the
  // containing block of the fixed backdrop, and stacked modals would not overlap.
  function portal(node: HTMLElement) {
    document.body.appendChild(node);
    return { destroy: () => node.remove() };
  }

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
    use:portal
    transition:fade={{ duration: dur(useFade ? MOTION.base : 0) }}
    role="presentation"
    onclick={handleBackdropClick}
  >
    <div
      class={`${modalClass}${size ? ` b2s-modal--${size}` : ''}${title ? ' b2s-modal--standard' : ''}`}
      bind:this={modalEl}
      in:pop={{ duration: useFly ? flyConfig.duration ?? MOTION.base : 0, y: flyConfig.y ?? 12 }}
      out:pop={{ duration: useFly ? MOTION.fast : 0, y: 6 }}
      role={role}
      aria-modal="true"
      aria-labelledby={ariaLabelledby ?? (title ? 'b2s-modal-title' : null)}
      tabindex="-1"
      onclick={handleModalClick}
      onkeydown={handleKeydown}
    >
      {#if title}
        <header class="b2s-modal__header">
          {#if iconClass}
            <span class="b2s-modal__icon" aria-hidden="true"><i class={iconClass}></i></span>
          {/if}
          <div class="b2s-modal__heading">
            <h2 id={ariaLabelledby ?? 'b2s-modal-title'}>{title}</h2>
            {#if subtitle}<p>{subtitle}</p>{/if}
          </div>
          {#if showClose}
            <button type="button" class="b2s-modal__close" aria-label={closeLabel} onclick={onClose}>
              <i class="bi bi-x-lg" aria-hidden="true"></i>
            </button>
          {/if}
        </header>
      {:else if showClose}
        <button class={closeClass} aria-label={closeLabel} onclick={onClose}>×</button>
      {/if}

      {#if wrapContent}
        <div class={contentClass}>
          {@render children?.()}
        </div>
      {:else}
        {@render children?.()}
      {/if}

      {#if footer}
        <footer class="b2s-modal__footer">
          {#if footerStart}
            <div class="b2s-modal__footer-start">{@render footerStart?.()}</div>
          {/if}
          {@render footer?.()}
        </footer>
      {/if}
    </div>
  </div>
{/if}
