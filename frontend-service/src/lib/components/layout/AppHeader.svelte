<script lang="ts">
  import { afterNavigate } from '$app/navigation';
  import { t } from '$lib/i18n';
  import { normalizeMe } from '$lib/types/me';
  import { initials } from '$lib/utils/format';
  import { live } from '$lib/stores/live';
  import { tasksPanelOpen } from '$lib/stores/tasks-panel';
  import LanguageSwitcher from '$lib/components/ui/LanguageSwitcher.svelte';
  import GlobalSearch from './GlobalSearch.svelte';
  import NotificationCenter from './NotificationCenter.svelte';
  import NavMenu from './NavMenu.svelte';
  import { activeItem, buildNav } from './nav';

  /**
   * The top bar of every page, instead of a side menu: ☰ opens the menu (same sections), the search takes the middle,
   * then the tasks in progress, the notifications and the account. The page below gets the whole width.
   */
  interface Props {
    user?: unknown;
    currentPath?: string;
    alertsCount?: number;
    criticalAlertsCount?: number;
    permissions?: { canSeeStorageRoots?: boolean; canSeeObservability?: boolean; canSeeAdmin?: boolean; features?: string[] } | null;
  }

  let { user = null, currentPath = '', alertsCount = 0, criticalAlertsCount = 0, permissions = null }: Props = $props();

  let me = $derived(normalizeMe(user));
  let admin = $derived(permissions?.canSeeAdmin === true || me?.is_admin === true);
  let staff = $derived(admin || permissions?.canSeeStorageRoots === true);
  let sections = $derived(buildNav({ admin, staff, features: permissions?.features ?? [],
    pending: $live.pending ?? Number(alertsCount ?? 0), critical: $live.critical ?? Number(criticalAlertsCount ?? 0) }));
  let here = $derived(activeItem(sections, currentPath));
  let currentTab = $derived.by(() => {
    const tabs = here?.item.tabs ?? [];
    let best = { href: '', length: -1 };
    for (const tab of tabs) {
      if ((currentPath === tab.href || currentPath.startsWith(`${tab.href}/`)) && tab.href.length > best.length) best = { href: tab.href, length: tab.href.length };
    }
    return best.href;
  });
  let name = $derived(String(me?.display_name || me?.username || me?.email || t('User')));
  let role = $derived(admin ? t('Administrator') : staff ? t('Guardian') : t('User'));
  let tasks = $derived(($live.tasks ?? []).length);

  // ---- menu and account ----
  let menuOpen = $state(false);
  let accountOpen = $state(false);
  afterNavigate(() => {
    menuOpen = false;
    accountOpen = false;
  });

  // ---- pages opened lately (this browser only) ----
  const RECENT_KEY = 'b2s.nav.recent';
  let recent = $state<Array<{ href: string; label: string }>>([]);
  $effect(() => {
    try {
      recent = JSON.parse(localStorage.getItem(RECENT_KEY) ?? '[]');
    } catch {
      recent = [];
    }
  });
  afterNavigate(({ to }) => {
    const path = to?.url.pathname;
    const entry = path ? activeItem(sections, path) : null;
    if (!path || !entry) return;
    const tab = (entry.item.tabs ?? []).find((item) => item.href === path);
    const page = { href: path, label: tab ? `${entry.item.label} · ${tab.label}` : entry.item.label };
    recent = [page, ...recent.filter((item) => item.href !== page.href && item.label !== page.label)].slice(0, 5);
    try {
      localStorage.setItem(RECENT_KEY, JSON.stringify(recent));
    } catch {
      /* private window: the list lives for this visit only */
    }
  });
</script>

<svelte:window onkeydown={(event) => accountOpen && event.key === 'Escape' && (accountOpen = false)} />

<header class="ah">
  <button type="button" class="ah__burger" class:is-on={menuOpen} aria-expanded={menuOpen} aria-label={t('Menu')} onclick={() => (menuOpen = !menuOpen)}>
    <i class={`bi ${menuOpen ? 'bi-x-lg' : 'bi-list'}`} aria-hidden="true"></i><span>{t('Menu')}</span>
  </button>
  <a href="/dashboard" class="ah__brand" aria-label="BornToShare"><span class="ah__logo" aria-hidden="true">B</span><b>BornToShare</b></a>
  <span class="ah__sep" aria-hidden="true"></span>
  <div class="ah__search"><GlobalSearch canSeeAdmin={admin} canSeeStorageRoots={staff} canSeeObservability={admin} /></div>
  <div class="ah__right">
    {#if admin}
      <button type="button" class="ah__icon" class:is-on={$tasksPanelOpen} aria-pressed={$tasksPanelOpen} onclick={() => tasksPanelOpen.update((value) => !value)}
        aria-label={tasks ? t('{count} task(s) in progress', { count: tasks }) : t('Recent tasks')} title={t('Recent tasks')}>
        <i class="bi bi-list-task" aria-hidden="true"></i>{#if tasks}<b class="ah__count">{tasks}</b>{/if}
      </button>
    {/if}
    <div class="ah__bell"><NotificationCenter /></div>
    <div class="ah__account">
      <button type="button" class="ah__me" aria-expanded={accountOpen} aria-haspopup="menu" onclick={() => (accountOpen = !accountOpen)}>
        <span class="ah__avatar" aria-hidden="true">{initials(name)}</span><span class="ah__name">{name}</span><i class="bi bi-chevron-down" aria-hidden="true"></i>
      </button>
      {#if accountOpen}
        <button type="button" class="ah__catch" aria-label={t('Close')} onclick={() => (accountOpen = false)}></button>
        <div class="ah__menu" role="menu">
          <div class="ah__who"><b>{name}</b><small>{role}</small></div>
          <LanguageSwitcher tone="light" />
          <form method="POST" action="/logout"><button type="submit" class="ah__menu-item" role="menuitem"><i class="bi bi-box-arrow-right" aria-hidden="true"></i>{t('Logout')}</button></form>
          <span class="ah__version" title={t('Built on {date}', { date: new Date(__B2S_BUILT_AT__).toLocaleString() })}>{__B2S_VERSION__}</span>
        </div>
      {/if}
    </div>
  </div>
</header>

<NavMenu open={menuOpen} {sections} current={here?.item.href ?? ''} {currentTab} {recent} onClose={() => (menuOpen = false)} />

<style>
  .ah { position: sticky; top: 0; z-index: 72; height: 52px; display: flex; align-items: center; gap: 12px; padding: 0 14px 0 8px; background: #0e1218; color: #fff; }
  .ah__burger { display: flex; align-items: center; gap: 8px; height: 38px; padding: 0 12px; border: 0; border-radius: 10px; background: transparent; color: #fff; font: inherit; font-size: 13px; font-weight: 500; cursor: pointer; }
  .ah__burger i { font-size: 20px; line-height: 1; }
  .ah__burger:hover, .ah__burger.is-on { background: #252b35; }
  .ah__brand { display: flex; align-items: center; gap: 8px; color: #fff; text-decoration: none; white-space: nowrap; }
  .ah__brand b { font-size: 15.5px; letter-spacing: -0.02em; }
  .ah__logo { width: 26px; height: 26px; display: flex; align-items: center; justify-content: center; border-radius: 8px; background: var(--b2s-accent); color: var(--b2s-on-accent); font-weight: 700; font-size: 14px; }
  .ah__sep { width: 1px; height: 24px; background: #3f4755; }
  .ah__search { flex: 1 1 auto; max-width: 720px; min-width: 0; }
  /* The search field of the bar, on the dark background (it opens the ⌘K palette) */
  .ah__search :global(.global-search-trigger) { width: 100%; height: 36px; border-color: #3f4755; background: #252b35; color: #b9bfca; }
  .ah__search :global(.global-search-trigger:hover) { border-color: #596273; background: #2b323d; }
  .ah__right { margin-left: auto; display: flex; align-items: center; gap: 4px; }
  .ah__icon { position: relative; width: 38px; height: 38px; display: flex; align-items: center; justify-content: center; border: 0; border-radius: 10px; background: transparent; color: #d1d5db; cursor: pointer; }
  .ah__icon i { font-size: 17px; }
  .ah__icon:hover, .ah__icon.is-on { background: #252b35; color: #fff; }
  .ah__count { position: absolute; top: 3px; right: 2px; min-width: 16px; height: 16px; padding: 0 4px; border-radius: 999px; background: #60a5fa; color: #0e1218; font-size: 10px; line-height: 16px; text-align: center; }
  .ah__bell :global(.nc-trigger) { border: 0; background: transparent; color: #d1d5db; }
  .ah__bell :global(.nc-trigger:hover) { background: #252b35; color: #fff; }
  .ah__bell :global(.nc-trigger.has-unread i) { color: #fff; }
  .ah__bell :global(.nc-badge) { border-color: #0e1218; }
  .ah__account { position: relative; }
  .ah__me { display: flex; align-items: center; gap: 8px; height: 38px; padding: 0 8px; border: 0; border-radius: 10px; background: transparent; color: #fff; font: inherit; font-size: 13px; cursor: pointer; }
  .ah__me:hover { background: #252b35; }
  .ah__me i { font-size: 10px; color: #8b93a3; }
  .ah__avatar { width: 28px; height: 28px; display: flex; align-items: center; justify-content: center; border-radius: 50%; background: var(--b2s-accent); color: var(--b2s-on-accent); font-size: 11px; font-weight: 700; }
  .ah__name { max-width: 160px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .ah__catch { position: fixed; inset: 0; z-index: 73; border: 0; background: transparent; cursor: default; }
  .ah__menu { position: absolute; right: 0; top: 44px; z-index: 74; width: 240px; display: grid; gap: 10px; padding: 12px; border: 1px solid var(--b2s-color-border-soft); border-radius: 12px;
    background: #fff; color: var(--b2s-color-text); box-shadow: 0 14px 34px rgba(14, 18, 24, 0.16); }
  .ah__who { display: grid; }
  .ah__who small { color: var(--b2s-color-text-muted); font-size: 12px; }
  .ah__menu form { margin: 0; }
  .ah__menu-item { width: 100%; display: flex; align-items: center; gap: 8px; height: 34px; padding: 0 8px; border: 0; border-radius: 8px; background: none; font: inherit; font-size: 13.5px; color: var(--b2s-color-text); cursor: pointer; }
  .ah__menu-item:hover { background: var(--b2s-color-surface-muted, #eef0f4); }
  .ah__version { color: var(--b2s-color-text-muted); font-size: 11px; }
</style>
