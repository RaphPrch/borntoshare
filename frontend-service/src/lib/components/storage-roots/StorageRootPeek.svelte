<script context="module" lang="ts">
  import type { StorageRootPermissionsData } from '$lib/api/storage-root-permissions';

  // One read per storage root and per page visit: the preview is a glance, the detail is one click away
  const cache = new Map<number, Promise<StorageRootPermissionsData | null>>();
</script>

<script lang="ts">
  import { onDestroy } from 'svelte';
  import { t } from '$lib/i18n';
  import { getStorageRootPermissions } from '$lib/api/storage-root-permissions';
  import type { StorageRootRow } from '$lib/utils/storage-roots';

  /** Preview of a storage root next to its row of the explorer, on hover: path, who reaches it, what is wrong. */
  export let row: StorageRootRow | null = null;
  export let anchor: HTMLElement | null = null;
  export let alert: { count: number; tone: 'warning' | 'error'; label?: string } | null = null;

  let shown: StorageRootRow | null = null;
  let position = { top: 0, left: 0 };
  let data: StorageRootPermissionsData | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let seq = 0;

  $: schedule(row, anchor);
  function schedule(next: StorageRootRow | null, element: HTMLElement | null) {
    if (timer) clearTimeout(timer);
    if (!next || !element) {
      shown = null;
      return;
    }
    // A short delay: moving the pointer down the list does not flash a card per row
    timer = setTimeout(async () => {
      const rect = element.getBoundingClientRect();
      position = { top: Math.max(8, Math.min(rect.top - 8, window.innerHeight - 220)), left: rect.right + 12 };
      shown = next;
      data = null;
      const id = Number(next.storage_root_id ?? next.id ?? 0);
      const current = ++seq;
      if (!cache.has(id)) cache.set(id, getStorageRootPermissions(fetch, id).catch(() => null));
      const result = await cache.get(id)!;
      if (current === seq) data = result;
    }, 350);
  }
  onDestroy(() => {
    if (timer) clearTimeout(timer);
  });

  $: pending = Number(shown?.pending_validation_count ?? 0);
  $: issue =
    data?.status === 'missing_ace'
      ? t('An AD group has lost its ACE')
      : data?.status === 'gap'
        ? t('{count} entry(ies) set outside BornToShare', { count: data.summary.gaps })
        : null;
</script>

{#if shown}
  <div class="peek" style={`top: ${position.top}px; left: ${position.left}px`} role="tooltip">
    <strong>{shown.storage_root_name ?? shown.storage_root_code}</strong>
    <code>{shown.root_path ?? ''}</code>
    {#if data?.summary.people}
      <span class="peek__split" aria-hidden="true">
        <span class="is-read" style={`flex: ${data.summary.read}`}></span><span class="is-write" style={`flex: ${data.summary.write}`}></span>
      </span>
    {/if}
    <span class="peek__line">
      {#if data}
        {data.acl_scanned_at
          ? t('{count} person(s) · {read} read · {write} modify', { count: data.summary.people, read: data.summary.read, write: data.summary.write })
          : t('ACL never read')}
      {:else}
        {t('Loading…')}
      {/if}
    </span>
    {#if pending}<span class="peek__line is-warn"><i></i>{t('{count} request(s) to decide', { count: pending })}</span>{/if}
    {#if alert?.count}<span class={`peek__line ${alert.tone === 'error' ? 'is-bad' : 'is-warn'}`}><i></i>{alert.label ?? t('{count} alerts', { count: alert.count })}</span>{/if}
    {#if issue}<span class="peek__line is-warn"><i></i>{issue}</span>{/if}
    {#if data?.inheritance?.broken}<span class="peek__line">{t('Inheritance broken')}</span>{/if}
  </div>
{/if}

<style>
  .peek {
    position: fixed;
    z-index: 60;
    width: 300px;
    display: grid;
    gap: 8px;
    padding: 14px 16px;
    border: 1px solid var(--b2s-color-border-soft);
    border-radius: 14px;
    background: var(--b2s-color-surface);
    box-shadow: 0 20px 50px rgba(15, 26, 58, 0.22);
    pointer-events: none;
  }

  strong {
    font-size: var(--b2s-fs-md);
  }

  code {
    color: var(--b2s-color-text-soft);
    font-family: var(--b2s-font-mono);
    font-size: 11px;
    overflow-wrap: anywhere;
  }

  .peek__split {
    display: flex;
    gap: 2px;
    height: 4px;
    overflow: hidden;
    border-radius: var(--b2s-radius-pill);
  }

  .peek__split .is-read { background: var(--b2s-color-info); }
  .peek__split .is-write { background: var(--b2s-color-warning); }

  .peek__line {
    display: flex;
    align-items: center;
    gap: 6px;
    color: var(--b2s-color-text-soft);
    font-size: var(--b2s-fs-xs);
  }

  .peek__line i {
    width: 7px;
    height: 7px;
    flex: none;
    border-radius: 50%;
    background: currentColor;
  }

  .peek__line.is-warn { color: var(--b2s-color-warning-strong); }
  .peek__line.is-bad { color: var(--b2s-color-danger-strong); }

  @media (hover: none) {
    .peek {
      display: none;
    }
  }
</style>
