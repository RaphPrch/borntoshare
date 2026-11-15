<script lang="ts">
  import { pulseOnIncrease } from '$lib/utils/motion';
  import { t } from '$lib/i18n';
  import { normalizeMe } from '$lib/types/me';
  import LanguageSwitcher from '$lib/components/ui/LanguageSwitcher.svelte';
  import { live } from '$lib/stores/live';
  import { activeItem, buildNav } from './nav';

  interface Props {
    /** Main navigation: a dark column on the left, four sections (Workspace, Governance, Storage Intelligence, Administration). */
    user?: unknown;
    currentPath?: string;
    alertsCount?: number;
    /** Open critical or high alerts (administrators only) */
    criticalAlertsCount?: number;
    permissions?: { canSeeStorageRoots?: boolean; canSeeObservability?: boolean; canSeeAdmin?: boolean; features?: string[] } | null;
  }

  let { user = null, currentPath = '', alertsCount = 0, criticalAlertsCount = 0, permissions = null }: Props = $props();

  let me = $derived(normalizeMe(user));
  let admin = $derived(permissions?.canSeeAdmin === true || me?.is_admin === true);
  // Administrators and guardians: the screens about folders; a user has his folders and his requests
  let staff = $derived(admin || permissions?.canSeeStorageRoots === true);
  let sections = $derived(
    buildNav({
      admin,
      staff,
      features: permissions?.features ?? [],
      pending: $live.pending ?? Number(alertsCount ?? 0),
      critical: $live.critical ?? Number(criticalAlertsCount ?? 0)
    })
  );
  let current = $derived(activeItem(sections, currentPath)?.item.href ?? '');
  const badge = (count: number) => (count > 99 ? '99+' : String(count));
</script>

<nav class="sb" aria-label={t('Main navigation')}>
  <a href="/dashboard" class="sb__brand" aria-label="BornToShare">
    <span class="sb__logo" aria-hidden="true">B</span>
    <span class="sb__name"><b>BornToShare</b><small>Governance · Storage Intelligence</small></span>
  </a>

  {#each sections as section (section.key)}
    <div class="sb__sec">{section.label}</div>
    {#each section.items as item (item.href)}
      <a href={item.href} class="sb__item" class:on={current === item.href} aria-current={current === item.href ? 'page' : undefined}>
        <i class={`bi ${item.icon}`} aria-hidden="true"></i>
        <span>{item.label}</span>
        {#if item.count}<b class="sb__badge" class:is-danger={item.danger} use:pulseOnIncrease={item.count}>{badge(item.count)}</b>{/if}
      </a>
    {/each}
  {/each}

  <div class="sb__foot">
    <LanguageSwitcher tone="dark" />
    <form method="POST" action="/logout">
      <button type="submit" class="sb__item sb__logout"><i class="bi bi-box-arrow-right" aria-hidden="true"></i><span>{t('Logout')}</span></button>
    </form>
    <span class="sb__version" title={t('Built on {date}', { date: new Date(__B2S_BUILT_AT__).toLocaleString() })}>{__B2S_VERSION__}</span>
  </div>
</nav>

<style>
  .sb {
    position: sticky;
    top: 0;
    z-index: 50;
    flex: 0 0 236px;
    width: 236px;
    height: 100vh;
    display: flex;
    flex-direction: column;
    gap: 1px;
    padding: 18px 12px 12px;
    overflow-y: auto;
    background: #0e1218;
    color: #c9ced8;
  }
  .sb__brand { display: flex; align-items: center; gap: 10px; padding: 2px 8px 14px; color: inherit; text-decoration: none; }
  .sb__logo { width: 34px; height: 34px; flex: none; display: flex; align-items: center; justify-content: center; border-radius: 10px;
    background: var(--b2s-accent); color: var(--b2s-on-accent); font-weight: 700; font-size: 17px; }
  .sb__name { display: grid; min-width: 0; }
  .sb__name b { color: #fff; font-size: 15px; letter-spacing: -0.01em; }
  .sb__name small { color: #8b93a3; font-size: 10.5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .sb__sec { padding: 16px 10px 6px; color: #6b7280; font-size: 10.5px; font-weight: 600; letter-spacing: 0.1em; text-transform: uppercase; }
  .sb__item {
    position: relative;
    width: 100%;
    min-height: 36px;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 7px 10px;
    border: 0;
    border-radius: 9px;
    background: transparent;
    color: #c9ced8;
    font: inherit;
    font-size: 13.5px;
    text-align: left;
    text-decoration: none;
    cursor: pointer;
    transition: background var(--b2s-motion-fast) var(--b2s-ease-out), color var(--b2s-motion-fast) var(--b2s-ease-out);
  }
  .sb__item i { width: 18px; font-size: 16px; line-height: 1; text-align: center; }
  .sb__item:hover { background: #1a1f27; color: #fff; }
  .sb__item.on { background: #1a1f27; color: var(--b2s-accent); font-weight: 600; }
  .sb__item.on::before { content: ''; position: absolute; left: -12px; top: 8px; bottom: 8px; width: 3px; border-radius: 0 3px 3px 0; background: var(--b2s-accent); }
  .sb__item:focus-visible { outline: 2px solid var(--b2s-accent); outline-offset: 1px; }
  .sb__badge { margin-left: auto; min-width: 20px; padding: 0 7px; border-radius: var(--b2s-radius-pill); background: var(--b2s-accent); color: var(--b2s-on-accent);
    font-size: 11px; font-weight: 700; line-height: 18px; text-align: center; }
  .sb__badge.is-danger { background: var(--b2s-color-danger-strong); color: #fff; }
  .sb__foot { margin-top: auto; padding: 16px 8px 0; display: grid; gap: 6px; justify-items: start; }
  .sb__foot form { width: 100%; margin: 0; }
  .sb__logout { color: #8b93a3; }
  .sb__version { padding: 0 2px; color: #6b7280; font-size: 10.5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 100%; }
</style>
