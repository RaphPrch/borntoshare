<script lang="ts">
  import { t } from '$lib/i18n';
  import { normalizeMe } from '$lib/types/me';
  import { initials } from '$lib/utils/format';
  import GlobalSearch from './GlobalSearch.svelte';
  import NotificationCenter from './NotificationCenter.svelte';
  import { activeItem, buildNav } from './nav';
  import { crumbs } from '$lib/stores/crumbs';

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
    {#if here}<span>{here.section.label}</span><i class="bi bi-chevron-right" aria-hidden="true"></i>
      {#if $crumbs.length}<a href={here.item.href}>{here.item.label}</a>{:else}<b>{here.item.label}</b>{/if}{/if}
    {#each $crumbs as crumb, index (index)}
      <i class="bi bi-chevron-right" aria-hidden="true"></i>
      {#if crumb.href && index < $crumbs.length - 1}<a href={crumb.href}>{crumb.label}</a>{:else}<b>{crumb.label}</b>{/if}
    {/each}
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
  .tb__crumb a { color: inherit; text-decoration: none; white-space: nowrap; }
  .tb__crumb a:hover { color: var(--b2s-color-text); text-decoration: underline; }
  .tb__search { margin-left: auto; }

  .tb__me { width: 36px; height: 36px; flex: none; display: flex; align-items: center; justify-content: center; border-radius: 50%;
    background: #0e1218; color: var(--b2s-accent); font-size: 12.5px; font-weight: 600; }
</style>
