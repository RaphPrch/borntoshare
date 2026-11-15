<script lang="ts">
  import { t } from '$lib/i18n';
  import { normalizeMe } from '$lib/types/me';
  import { initials } from '$lib/utils/format';
  import GlobalSearch from './GlobalSearch.svelte';
  import NotificationCenter from './NotificationCenter.svelte';
  import { activeItem, buildNav } from './nav';

  interface Props {
    /** Sticky bar over every page: where you are (section › page), the ⌘K search, the notifications and who is signed in. */
    user?: unknown;
    currentPath?: string;
    permissions?: { canSeeStorageRoots?: boolean; canSeeObservability?: boolean; canSeeAdmin?: boolean; features?: string[] } | null;
  }

  let { user = null, currentPath = '', permissions = null }: Props = $props();

  let me = $derived(normalizeMe(user));
  let admin = $derived(permissions?.canSeeAdmin === true || me?.is_admin === true);
  let staff = $derived(admin || permissions?.canSeeStorageRoots === true);
  let here = $derived(activeItem(buildNav({ admin, staff, features: permissions?.features ?? [], pending: 0, critical: 0 }), currentPath));
  let name = $derived(String(me?.display_name || me?.username || me?.email || t('User')));
  let role = $derived(admin ? t('Administrator') : staff ? t('Guardian') : t('User'));
</script>

<header class="tb">
  <div class="tb__crumb">
    {#if here}<span>{here.section.label}</span><i class="bi bi-chevron-right" aria-hidden="true"></i><b>{here.item.label}</b>{/if}
  </div>
  <div class="tb__search">
    <GlobalSearch canSeeAdmin={admin} canSeeStorageRoots={staff} canSeeObservability={admin} />
  </div>
  <div class="tb__bell"><NotificationCenter /></div>
  <span class="tb__me" title={`${name} · ${role}`} aria-label={`${name} · ${role}`}>{initials(name)}</span>
</header>

<style>
  .tb {
    position: sticky;
    top: 0;
    /* Above the side menu (50): the drawers it holds (notifications, ⌘K) cover the whole page */
    z-index: 60;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 11px 28px;
    border-bottom: 1px solid var(--b2s-color-border-soft);
    /* Plain white, no backdrop-filter: a filter would make the bar the containing block of the fixed drawers inside
       it (notifications, ⌘K) and trap them under its 60 px instead of over the page */
    background: #fff;
  }
  .tb__crumb { display: flex; align-items: center; gap: 6px; min-width: 0; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .tb__crumb i { font-size: 10px; }
  .tb__crumb b { color: var(--b2s-color-text); font-weight: 600; white-space: nowrap; }
  .tb__search { margin-left: auto; }

  /* The ⌘K palette and the bell, drawn for the bar instead of the old rail */
  .tb__search :global(.global-search-trigger) {
    width: 320px;
    min-height: 38px;
    height: 38px;
    flex-direction: row;
    justify-content: flex-start;
    gap: 8px;
    padding: 0 12px;
    border: 1px solid var(--b2s-color-border-soft);
    border-radius: 11px;
    background: var(--b2s-color-surface-soft);
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-sm);
  }
  .tb__search :global(.global-search-trigger i) { font-size: 14px; }
  .tb__search :global(.global-search-trigger:hover) { border-color: var(--b2s-color-border); background: var(--b2s-color-surface); }
  .tb__search :global(.global-search-trigger::after) { content: '⌘K'; margin-left: auto; padding: 0 6px; border: 1px solid var(--b2s-color-border); border-radius: 6px;
    background: var(--b2s-color-surface); color: var(--b2s-color-text-muted); font-size: 11px; font-weight: 600; }
  .tb__bell :global(.nc-trigger) { width: 38px; min-height: 38px; height: 38px; padding: 0; border: 1px solid var(--b2s-color-border-soft); border-radius: 11px;
    background: var(--b2s-color-surface); }
  .tb__bell :global(.nc-trigger > span) { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
  .tb__bell :global(.nc-trigger i) { font-size: 16px; }
  .tb__bell :global(.nc-badge) { top: -6px; right: -6px; border: 2px solid #fff; }
  .tb__me { width: 36px; height: 36px; flex: none; display: flex; align-items: center; justify-content: center; border-radius: 50%;
    background: #0e1218; color: var(--b2s-accent); font-size: 12.5px; font-weight: 600; }
</style>
