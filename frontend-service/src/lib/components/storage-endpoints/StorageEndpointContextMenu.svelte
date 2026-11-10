<script context="module" lang="ts">
  export type EndpointMenuAction = 'test' | 'edit' | 'add-folders' | 'share' | 'delete';
</script>

<script lang="ts">
  import { tick } from 'svelte';
  import { fade } from 'svelte/transition';
  import { dur, MOTION, pop } from '$lib/utils/motion';
  import { t } from '$lib/i18n';

  /** Right-click menu of a file server in the list: test it, edit it, add folders or a share, delete it. */
  export let endpoint: Record<string, any> | null = null;
  export let at = { x: 0, y: 0 };
  /** Folders attached to it: it cannot be deleted while there are some */
  export let folderCount = 0;
  export let testing = false;
  export let onClose: () => void = () => {};
  export let onAction: (kind: EndpointMenuAction, endpoint: Record<string, any>) => void = () => {};

  let menuEl: HTMLDivElement | null = null;
  let position = { left: 0, top: 0 };

  $: inactive = endpoint ? endpoint.is_active === false || endpoint.is_active === 0 || String(endpoint.status ?? '').toLowerCase() === 'disabled' : false;
  $: items = endpoint
    ? [
        { key: 'test' as const, label: testing ? t('Testing…') : t('Test the connection'), icon: 'bi-activity', disabled: testing, hint: '' },
        { key: 'edit' as const, label: t('Edit'), icon: 'bi-pencil', disabled: false, hint: '' },
        { key: 'add-folders' as const, label: t('Add folders'), icon: 'bi-plus-lg', disabled: inactive, hint: inactive ? t('This file server is disabled') : '' },
        { key: 'share' as const, label: t('Create a share'), icon: 'bi-folder-plus', disabled: inactive, hint: inactive ? t('This file server is disabled') : '' },
        {
          key: 'delete' as const,
          label: t('Delete storage endpoint'),
          icon: 'bi-trash',
          danger: true,
          disabled: folderCount > 0,
          hint: folderCount > 0 ? t('{count} folder(s) attached: remove them from BornToShare first', { count: folderCount }) : ''
        }
      ]
    : [];

  $: if (endpoint) void place();
  async function place() {
    await tick();
    const width = menuEl?.offsetWidth ?? 240;
    const height = menuEl?.offsetHeight ?? 200;
    // Kept inside the window
    position = { left: Math.min(at.x, window.innerWidth - width - 8), top: Math.min(at.y, window.innerHeight - height - 8) };
    menuEl?.querySelector<HTMLButtonElement>('button:not([disabled])')?.focus();
  }

  function pick(item: (typeof items)[number]) {
    // Closing the menu clears `endpoint` at once (the parent owns it): keep the target first
    const target = endpoint;
    if (item.disabled || !target) return;
    onClose();
    onAction(item.key, target);
  }

  function onKeydown(event: KeyboardEvent) {
    if (!endpoint) return;
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
    if (endpoint && menuEl && !menuEl.contains(event.target as Node)) onClose();
  }
</script>

<svelte:window on:keydown={onKeydown} on:pointerdown={onPointerDown} on:scroll|capture={() => endpoint && onClose()} on:resize={() => endpoint && onClose()} />

{#if endpoint}
  <div bind:this={menuEl} class="cm" role="menu" aria-label={t('Actions on {name}', { name: String(endpoint.name ?? '') })}
    in:pop={{ duration: MOTION.fast, y: -4, scale: 0.96 }} out:fade={{ duration: dur(MOTION.fast) }}
    style={`left: ${position.left}px; top: ${position.top}px`}>
    <div class="cm__head">
      <strong>{endpoint.name ?? ''}</strong>
      {#if inactive}<small>{t('Disabled')}</small>{/if}
    </div>
    {#each items as item (item.key)}
      {#if item.key === 'delete'}<hr />{/if}
      <button type="button" role="menuitem" class="cm__item" class:is-danger={item.danger} disabled={item.disabled}
        title={item.hint || undefined} on:click={() => pick(item)}>
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
    color: var(--b2s-color-warning-strong);
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
