<script lang="ts">
  import { t } from '$lib/i18n';
  export let user: unknown = null;
  import { type MegaMenuKey } from '$lib/components/layout/mega-config';
  import { normalizeMe } from '$lib/types/me';
  import { initials } from '$lib/utils/format';
  import LanguageSwitcher from '$lib/components/ui/LanguageSwitcher.svelte';
  import GlobalSearch from '$lib/components/layout/GlobalSearch.svelte';

  export let activeMega: MegaMenuKey | null = null;
  export let currentPath: string | undefined = undefined;
  export let alertsCount = 0;
  /** Open critical or high alerts (administrators only) */
  export let criticalAlertsCount = 0;
  export let permissions: {
    canSeeStorageRoots?: boolean;
    canSeeObservability?: boolean;
    canSeeAdmin?: boolean;
  } | null = null;

  const openMega = (key: MegaMenuKey) => {
    activeMega = activeMega === key ? null : key;
  };

  // Show admin menu only for admins (RBAC → platform_admin is mapped to admin in the UI)
  $: me = normalizeMe(user);
  $: canSeeAdmin = permissions?.canSeeAdmin === true || me?.is_admin === true;
  $: canSeeStorageRoots = permissions?.canSeeStorageRoots === true;
  $: canSeeObservability = permissions?.canSeeObservability === true;

  type TopbarNavKey = MegaMenuKey | 'dashboard' | 'requests' | 'observability';

  const routeMap: Record<TopbarNavKey, string[]> = {
    dashboard: ['/dashboard'],
    storageRoots: ['/storage-roots'],
    requests: ['/access-requests'],
    observability: ['/observability'],
    admin: ['/admin']
  };

  const isActive = (key: TopbarNavKey) => {
    if (activeMega === key) return true;
    const path = currentPath ?? '';
    const prefixes = routeMap[key] ?? [`/${key}`];
    return prefixes.some(prefix => path.startsWith(prefix));
  };

  // ============================================================
  // 🧼 NORMALISATION ULTRA ROBUSTE DU USER
  // - object
  // - string JSON
  // - string simple
  // - null / undefined
  // ============================================================

  type ViewUser = {
    label: string;
    initials: string;
  };

  let viewUser: ViewUser = {
    label: t('User'),
    initials: 'U'
  };

  function normalizeUser(input: unknown): ViewUser {
    let label = t('User');

    let u: any = null;

    // 🟡 CAS 1 — string JSON
    if (typeof input === 'string') {
      try {
        u = JSON.parse(input);
      } catch {
        // string simple → on l’ignore
        u = null;
      }
    }

    // 🟢 CAS 2 — object direct
    if (!u && typeof input === 'object' && input !== null) {
      u = input;
    }

    if (u && typeof u === 'object') {
      if (typeof u.display_name === 'string') {
        label = u.display_name;
      } else if (typeof u.username === 'string') {
        label = u.username;
      } else if (typeof u.email === 'string') {
        label = u.email;
      }
    }

    return {
      label,
      initials: initials(label, 'U')
    };
  }

  // 🔁 Réactivité Svelte
  $: viewUser = normalizeUser(user);
  $: hasAlerts = Number(alertsCount ?? 0) > 0;
  $: hasCritical = Number(criticalAlertsCount ?? 0) > 0;
</script>

<nav class="b2s-topbar">
  <!-- LEFT -->
  <div class="topbar-left">
    <!-- Logo -->
    <a href="/dashboard" class="logo">
      <div class="logo-text">
        <div class="logo-title">BornToShare</div>
      </div>
    </a>

    <!-- Navigation -->
    <div class="main-nav">
      <a
        href="/dashboard"
        class="nav-item {isActive('dashboard') ? 'active' : ''}"
      >
        {t('Dashboard')}
      </a>

      {#if canSeeStorageRoots}
        <a
          href="/storage-roots"
          class="nav-item {isActive('storageRoots') ? 'active' : ''}"
        >
          {t('Storage Roots')}
        </a>
      {/if}

      <a
        href="/access-requests"
        class="nav-item {isActive('requests') ? 'active' : ''}"
      >
        {t('Requests')}
      </a>

      {#if canSeeObservability}
        <a
          href="/observability"
          class="nav-item {isActive('observability') ? 'active' : ''}"
        >
          {t('Observability')}
        </a>
      {/if}

      {#if canSeeAdmin}
        <button
          type="button"
          class="nav-item {isActive('admin') ? 'active' : ''}"
          on:click={() => openMega('admin')}
        >
          {t('Admin')}
        </button>
      {/if}
    </div>
  </div>

  <!-- RIGHT -->
  <div class="topbar-right">
    <div class="user-menu-wrapper">
      <GlobalSearch {canSeeAdmin} {canSeeStorageRoots} {canSeeObservability} />
      <LanguageSwitcher />

      <a href="/access-requests?status=pending" class="topbar-pill" class:is-on={hasAlerts} title={t('Pending access requests')}>
        <i class="bi bi-inbox" aria-hidden="true"></i><span class="topbar-label">{t('Requests')}</span>
        <span class="topbar-pill__count">{alertsCount > 99 ? '99+' : alertsCount}</span>
      </a>
      {#if canSeeObservability}
        <a href="/observability?tab=alerts&severity=critical_high" class="topbar-pill topbar-pill--danger" class:is-on={hasCritical} title={t('Open critical alerts')}>
          <i class="bi bi-exclamation-triangle" aria-hidden="true"></i><span class="topbar-label">{t('Alerts')}</span>
          <span class="topbar-pill__count">{criticalAlertsCount > 99 ? '99+' : criticalAlertsCount}</span>
        </a>
      {/if}

      <div class="topbar-user-chip" aria-label={t('Signed-in user {label}', { label: viewUser.label })}>
        <span class="topbar-user-avatar">{viewUser.initials}</span>
        <span class="topbar-user-name">{viewUser.label}</span>
      </div>

      <form method="POST" action="/logout">
        <button type="submit" class="logout-btn" aria-label={t('Logout')}>
        <i class="bi bi-box-arrow-right" aria-hidden="true"></i>
        <span class="topbar-label">{t('Logout')}</span>
        </button>
      </form>
    </div>
  </div>
</nav>
