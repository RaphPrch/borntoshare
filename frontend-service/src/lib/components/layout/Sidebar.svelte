<script lang="ts">
  import { pulseOnIncrease } from '$lib/utils/motion';
  import { t } from '$lib/i18n';
  import { normalizeMe } from '$lib/types/me';
  import { initials } from '$lib/utils/format';
  import LanguageSwitcher from '$lib/components/ui/LanguageSwitcher.svelte';
  import GlobalSearch from '$lib/components/layout/GlobalSearch.svelte';
  import NotificationCenter from '$lib/components/layout/NotificationCenter.svelte';
  import { live } from '$lib/stores/live';

  
  
  interface Props {
    /** Main navigation of the app: a rail on the left, the pages take the whole height. */
    user?: unknown;
    currentPath?: string;
    alertsCount?: number;
    /** Open critical or high alerts (administrators only) */
    criticalAlertsCount?: number;
    permissions?: {
    canSeeStorageRoots?: boolean;
    canSeeObservability?: boolean;
    canSeeAdmin?: boolean;
    features?: string[];
  } | null;
  }

  let {
    user = null,
    currentPath = '',
    alertsCount = 0,
    criticalAlertsCount = 0,
    permissions = null
  }: Props = $props();

  let me = $derived(normalizeMe(user));
  let canSeeAdmin = $derived(permissions?.canSeeAdmin === true || me?.is_admin === true);
  let canSeeStorageRoots = $derived(permissions?.canSeeStorageRoots === true);
  let canSeeObservability = $derived(permissions?.canSeeObservability === true);
  // Optional modules switched on (Advanced settings › Features)
  let features = $derived(permissions?.features ?? []);
  let governance = $derived(features.includes('governance'));

  type Item = { href: string; label: string; icon: string; count?: number; danger?: boolean };
  // Badges follow the live updates once connected; the values of the page load until then
  let pendingCount = $derived($live.pending ?? Number(alertsCount ?? 0));
  let criticalCount = $derived($live.critical ?? Number(criticalAlertsCount ?? 0));

  let main = $derived([
    { href: '/dashboard', label: t('Dashboard'), icon: 'bi-speedometer2' },
    // Everyone has these four menus; their content follows the role (own folders and own activity for a user)
    { href: '/storage-roots', label: t('Folders'), icon: 'bi-folder2-open' },
    ...(governance ? [{ href: '/exposure', label: t('Exposure'), icon: 'bi-shield-exclamation' }] : []),
    // Lean 5S of the shares, and the printable reports (on the folders the person may see)
    ...(features.includes('fives') ? [{ href: '/five-s', label: t('5S'), icon: 'bi-stars' }] : []),
    { href: '/reports', label: t('Reports'), icon: 'bi-file-earmark-bar-graph' },
    ...(governance ? [{ href: '/access-requests', label: t('Requests'), icon: 'bi-check2-square', count: pendingCount }] : []),
    { href: '/observability', label: t('Monitoring'), icon: 'bi-activity', count: canSeeObservability ? criticalCount : 0, danger: true }
  ] as Item[]);
  let admin = $derived((canSeeAdmin
    ? [
        { href: '/admin/storage-endpoints', label: t('Servers'), icon: 'bi-hdd-network' },
        { href: '/admin/zones', label: t('Zones'), icon: 'bi-geo-alt' },
        { href: '/admin/identity-sources', label: t('Directories'), icon: 'bi-diagram-3' },
        { href: '/admin/identity', label: t('Identities'), icon: 'bi-people' },
        { href: '/admin/tags', label: t('Tags'), icon: 'bi-tags' },
        { href: '/admin/policies', label: t('Policies'), icon: 'bi-lightning-charge' },
        { href: '/admin/advanced-settings', label: t('Settings'), icon: 'bi-sliders' }
      ]
    : []) as Item[]);

  const isActive = (href: string, path: string) => path === href || path.startsWith(`${href}/`);
  const badge = (count: number) => (count > 99 ? '99+' : String(count));

  function displayName(input: unknown): string {
    const u = input as { display_name?: unknown; username?: unknown; email?: unknown } | null;
    return String(u?.display_name || u?.username || u?.email || t('User'));
  }
  let name = $derived(displayName(me ?? user));
</script>

<nav class="sb" aria-label={t('Main navigation')}>
  <a href="/dashboard" class="sb__logo" aria-label="BornToShare">B</a>

  <div class="sb__group">
    {#each main as item (item.href)}
      <a href={item.href} class="sb__item" class:on={isActive(item.href, currentPath)} aria-current={isActive(item.href, currentPath) ? 'page' : undefined}>
        <i class={`bi ${item.icon}`} aria-hidden="true"></i>
        <span>{item.label}</span>
        {#if item.count}<b class="sb__badge" class:is-danger={item.danger} use:pulseOnIncrease={item.count}>{badge(item.count)}</b>{/if}
      </a>
    {/each}
  </div>

  {#if admin.length}
    <div class="sb__group sb__group--admin">
      {#each admin as item (item.href)}
        <a href={item.href} class="sb__item" class:on={isActive(item.href, currentPath)} aria-current={isActive(item.href, currentPath) ? 'page' : undefined}>
          <i class={`bi ${item.icon}`} aria-hidden="true"></i>
          <span>{item.label}</span>
        </a>
      {/each}
    </div>
  {/if}

  <div class="sb__bottom">
    <!-- Tools as icons, two per line: the rail stays whole on a 900 px high screen (labels in the tooltips) -->
    <div class="sb__tools">
      <NotificationCenter />
      <GlobalSearch {canSeeAdmin} {canSeeStorageRoots} {canSeeObservability} />
      <form method="POST" action="/logout">
        <button type="submit" class="sb__item sb__logout" aria-label={t('Logout')} title={t('Logout')}>
          <i class="bi bi-box-arrow-right" aria-hidden="true"></i>
          <span>{t('Logout')}</span>
        </button>
      </form>
    </div>
    <LanguageSwitcher tone="light" />
    <span class="sb__version" title={t('Built on {date}', { date: new Date(__B2S_BUILT_AT__).toLocaleString() })}>{__B2S_VERSION__}</span>
  </div>
</nav>

<style>
  .sb__version { display: block; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--b2s-color-text-muted); font-size: 10px; text-align: center; opacity: 0.8; }
  .sb {
    position: sticky;
    top: 0;
    z-index: 50;
    flex: 0 0 88px;
    width: 88px;
    height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
    padding: 14px 0 10px;
    overflow-y: auto;
    border-right: 1px solid var(--b2s-color-border-soft);
    background: var(--b2s-color-surface);
  }

  .sb__logo {
    width: 40px;
    height: 40px;
    flex: none;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-bottom: 4px;
    border-radius: 12px;
    background: var(--b2s-accent);
    color: var(--b2s-on-accent);
    font-weight: 700;
    text-decoration: none;
  }

  .sb__group {
    width: 100%;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
  }

  .sb__group--admin {
    padding-top: 8px;
    border-top: 1px solid var(--b2s-color-border-soft);
  }

  .sb__item {
    position: relative;
    width: 74px;
    min-height: 50px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 2px;
    padding: 0 2px;
    border: 0;
    border-radius: 12px;
    background: transparent;
    color: var(--b2s-color-text-muted);
    font: inherit;
    font-size: 11px;
    line-height: 1.2;
    text-align: center;
    text-decoration: none;
    cursor: pointer;
  }

  .sb__item i {
    font-size: 18px;
    line-height: 1;
  }

  .sb__item:hover {
    background: var(--b2s-color-neutral-soft);
    color: var(--b2s-color-text);
  }

  .sb__item.on {
    background: var(--b2s-accent-soft);
    color: var(--b2s-accent-strong);
    font-weight: 600;
  }

  .sb__badge {
    position: absolute;
    top: 3px;
    right: 8px;
    min-width: 17px;
    padding: 0 4px;
    border-radius: var(--b2s-radius-pill);
    background: var(--b2s-color-text);
    color: var(--b2s-color-surface);
    font-size: 10px;
    font-weight: 600;
    line-height: 17px;
  }

  .sb__badge.is-danger {
    background: var(--b2s-color-danger-strong);
  }

  .sb__tools { display: grid; grid-template-columns: repeat(2, 36px); gap: 4px 8px; justify-content: center; }
  .sb__tools form { margin: 0; }
  .sb__tools :global(.nc-trigger),
  .sb__tools :global(.global-search-trigger),
  .sb__tools .sb__item { width: 36px; min-height: 36px; height: 36px; padding: 0; border-radius: 10px; }
  .sb__tools :global(.nc-trigger > span),
  .sb__tools :global(.global-search-trigger > span),
  .sb__tools .sb__item > span { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
  .sb__tools :global(.nc-badge) { top: -4px; right: -6px; }
  /* A lower screen: the menu items tighten so that the whole rail fits */
  @media (max-height: 960px) {
    .sb__item { min-height: 44px; }
    .sb { gap: 4px; }
  }

  .sb__bottom {
    width: 100%;
    margin-top: auto;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
    padding-top: 8px;
  }

  .sb__user {
    width: 32px;
    height: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    background: var(--b2s-color-neutral-soft);
    color: var(--b2s-color-text);
    font-size: 11px;
    font-weight: 600;
  }

  .sb__logout {
    min-height: 44px;
  }
</style>
