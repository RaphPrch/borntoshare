<script lang="ts">
  import { tick } from 'svelte';
  import { t } from '$lib/i18n';
  import type { StorageRootRow } from '$lib/utils/storage-roots';
  import type { FolderActionKind } from '$lib/components/storage-roots/StorageRootFolderActions.svelte';

  /** Right-click menu of a storage root in the explorer: open it, and the operations on its folder on the file server. */
  export let row: StorageRootRow | null = null;
  export let at = { x: 0, y: 0 };
  export let onClose: () => void = () => {};
  export let onOpen: (row: StorageRootRow) => void = () => {};
  export let onAction: (kind: FolderActionKind, row: StorageRootRow) => void = () => {};

  let menuEl: HTMLDivElement | null = null;
  let position = { left: 0, top: 0 };

  $: broken = row?.inheritance_broken;
  $: items = row
    ? [
        { key: 'open', label: t('Open'), icon: 'bi-box-arrow-in-right', run: (target: StorageRootRow) => onOpen(target) },
        {
          key: 'inheritance',
          label: broken ? t('Restore the inheritance') : t('Break the inheritance'),
          icon: broken ? 'bi-diagram-3' : 'bi-scissors',
          disabled: broken == null,
          hint: broken == null ? t('Read the ACL first') : '',
          run: (target: StorageRootRow) => onAction('inheritance', target)
        },
        { key: 'subfolder', label: t('New sub-folder'), icon: 'bi-folder-plus', run: (target: StorageRootRow) => onAction('subfolder', target) },
        { key: 'delete', label: t('Delete the folder from the server'), icon: 'bi-trash', danger: true, run: (target: StorageRootRow) => onAction('delete', target) }
      ]
    : [];

  $: if (row) void place();
  async function place() {
    await tick();
    const width = menuEl?.offsetWidth ?? 240;
    const height = menuEl?.offsetHeight ?? 180;
    // Kept inside the window
    position = { left: Math.min(at.x, window.innerWidth - width - 8), top: Math.min(at.y, window.innerHeight - height - 8) };
    menuEl?.querySelector<HTMLButtonElement>('button:not([disabled])')?.focus();
  }

  function pick(item: (typeof items)[number]) {
    // Closing the menu clears `row` at once (the parent owns it): keep the target first
    const target = row;
    if (item.disabled || !target) return;
    onClose();
    item.run(target);
  }

  function onKeydown(event: KeyboardEvent) {
    if (!row) return;
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
    if (row && menuEl && !menuEl.contains(event.target as Node)) onClose();
  }
</script>

<svelte:window on:keydown={onKeydown} on:pointerdown={onPointerDown} on:scroll|capture={() => row && onClose()} on:resize={() => row && onClose()} />

{#if row}
  <div bind:this={menuEl} class="cm" role="menu" aria-label={t('Actions on {name}', { name: String(row.storage_root_name ?? '') })}
    style={`left: ${position.left}px; top: ${position.top}px`}>
    <div class="cm__head">
      <strong>{row.storage_root_name ?? row.storage_root_code}</strong>
      <small>{row.root_path ?? ''}</small>
    </div>
    {#each items as item (item.key)}
      {#if item.key === 'delete'}<hr />{/if}
      <button type="button" role="menuitem" class="cm__item" class:is-danger={item.danger} disabled={item.disabled}
        title={item.hint || undefined} on:click={() => pick(item)}>
        <i class={`bi ${item.icon}`} aria-hidden="true"></i>{item.label}
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
    font-family: var(--b2s-font-mono);
    font-size: 11px;
    overflow-wrap: anywhere;
  }

  .cm__item {
    display: flex;
    align-items: center;
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

  hr {
    width: 100%;
    margin: 4px 0;
    border: 0;
    border-top: 1px solid var(--b2s-color-border-soft);
  }
</style>
