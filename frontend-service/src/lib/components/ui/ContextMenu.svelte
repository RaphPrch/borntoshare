<script module lang="ts">
  export type ContextMenuItem = {
    key: string;
    label: string;
    icon: string;
    disabled?: boolean;
    /** Why it is disabled (shown under the label) */
    hint?: string;
    danger?: boolean;
    /** A separator above it */
    separated?: boolean;
  };

  /** Where to open for a right click (the context-menu key gives no pointer position: under the row) */
  export function menuPositionFor(event: MouseEvent): { x: number; y: number } {
    const rect = (event.currentTarget as HTMLElement | null)?.getBoundingClientRect();
    return event.clientX || event.clientY ? { x: event.clientX, y: event.clientY } : { x: (rect?.left ?? 0) + 24, y: rect?.bottom ?? 0 };
  }
</script>

<script lang="ts">

  import { tick } from 'svelte';
  import { fade } from 'svelte/transition';
  import { dur, MOTION, pop } from '$lib/utils/motion';
  import { t } from '$lib/i18n';

  
  interface Props {
    /** Right-click menu of an item of a list (zone, directory…): its actions, the impossible ones greyed with why. */
    open?: boolean;
    title?: string;
    subtitle?: string;
    items?: ContextMenuItem[];
    at?: any;
    onClose?: () => void;
    onPick?: (key: string) => void;
  }

  let {
    open = false,
    title = '',
    subtitle = '',
    items = [],
    at = { x: 0, y: 0 },
    onClose = () => {},
    onPick = () => {}
  }: Props = $props();

  let menuEl: HTMLDivElement | null = $state(null);
  let position = $state({ left: 0, top: 0 });

  async function place() {
    await tick();
    const width = menuEl?.offsetWidth ?? 240;
    const height = menuEl?.offsetHeight ?? 200;
    // Kept inside the window
    position = { left: Math.min(at.x, window.innerWidth - width - 8), top: Math.min(at.y, window.innerHeight - height - 8) };
    menuEl?.querySelector<HTMLButtonElement>('button:not([disabled])')?.focus();
  }

  function pick(item: ContextMenuItem) {
    if (item.disabled) return;
    // The action first: closing clears the target the parent keeps
    onPick(item.key);
    onClose();
  }

  function onKeydown(event: KeyboardEvent) {
    if (!open) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      onClose();
      return;
    }
    if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
    event.preventDefault();
    const buttons = [...(menuEl?.querySelectorAll<HTMLButtonElement>('button:not([disabled])') ?? [])];
    const index = buttons.indexOf(document.activeElement as HTMLButtonElement);
    const next = event.key === 'ArrowDown' ? (index + 1) % buttons.length : (index - 1 + buttons.length) % buttons.length;
    buttons[next]?.focus();
  }

  function onPointerDown(event: PointerEvent) {
    if (open && menuEl && !menuEl.contains(event.target as Node)) onClose();
  }

  $effect(() => {
    if (open) void place();
  });
</script>

<svelte:window onkeydown={onKeydown} onpointerdown={onPointerDown} onscrollcapture={() => open && onClose()} onresize={() => open && onClose()} />

{#if open}
  <div bind:this={menuEl} class="cm" role="menu" aria-label={t('Actions on {name}', { name: title })}
    in:pop={{ duration: MOTION.fast, y: -4, scale: 0.96 }} out:fade={{ duration: dur(MOTION.fast) }}
    style={`left: ${position.left}px; top: ${position.top}px`}>
    <div class="cm__head">
      <strong>{title}</strong>
      {#if subtitle}<small>{subtitle}</small>{/if}
    </div>
    {#each items as item (item.key)}
      {#if item.separated}<hr />{/if}
      <button type="button" role="menuitem" class="cm__item" class:is-danger={item.danger} disabled={item.disabled}
        title={item.hint || undefined} onclick={() => pick(item)}>
        <i class={`bi ${item.icon}`} aria-hidden="true"></i>
        <span>{item.label}{#if item.disabled && item.hint}<small>{item.hint}</small>{/if}</span>
      </button>
    {/each}
  </div>
{/if}

<style>
  .cm {
    position: fixed;
    z-index: 70;
    min-width: 240px;
    max-width: 320px;
    display: grid;
    padding: 6px;
    border: 1px solid var(--b2s-color-border-soft);
    border-radius: 12px;
    background: var(--b2s-color-surface);
    box-shadow: 0 18px 44px rgba(15, 26, 58, 0.22);
    transform-origin: top left;
  }

  .cm__head {
    display: grid;
    gap: 2px;
    padding: 6px 10px 8px;
    border-bottom: 1px solid var(--b2s-color-border-soft);
    margin-bottom: 4px;
  }

  .cm__head strong {
    font-size: var(--b2s-fs-sm);
  }

  .cm__head small {
    color: var(--b2s-color-text-muted);
    font-size: 11px;
  }

  .cm__item {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 8px 10px;
    border: 0;
    border-radius: 8px;
    background: none;
    color: var(--b2s-color-text);
    font: inherit;
    font-size: var(--b2s-fs-sm);
    text-align: left;
    cursor: pointer;
  }

  .cm__item i {
    margin-top: 2px;
  }

  .cm__item span {
    display: grid;
    gap: 2px;
  }

  .cm__item small {
    color: var(--b2s-color-text-muted);
    font-size: 11px;
  }

  .cm__item:hover:not([disabled]),
  .cm__item:focus-visible {
    background: var(--b2s-color-surface-soft);
    outline: none;
  }

  .cm__item[disabled] {
    color: var(--b2s-color-text-faint);
    cursor: default;
  }

  .cm__item.is-danger {
    color: var(--b2s-color-danger-strong);
  }

  .cm__item.is-danger[disabled] {
    color: var(--b2s-color-text-faint);
  }

  hr {
    width: 100%;
    margin: 4px 0;
    border: 0;
    border-top: 1px solid var(--b2s-color-border-soft);
  }
</style>
