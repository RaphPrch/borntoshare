<script lang="ts">
  export let user: unknown = null;
  import { type MegaMenuKey } from '$lib/components/mega-config.ts';
  import { normalizeMe } from '$lib/auth/me';
  import { initialsFromLabel } from '$lib/utils/initials';

  export let activeMega: MegaMenuKey | null = null;
  export let currentPath: string | undefined = undefined;
  export let alertsCount = 0;
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

  type TopbarNavKey = MegaMenuKey | 'dashboard' | 'requests';

  const routeMap: Record<TopbarNavKey, string[]> = {
    dashboard: ['/dashboard'],
    storageRoots: ['/storage-roots'],
    requests: ['/access-requests'],
    observability: ['/admin/observability'],
    admin: ['/admin']
  };

  const isActive = (key: TopbarNavKey) => {
    if (activeMega === key) return true;
    const path = currentPath ?? '';
    if (key === 'observability') return path.startsWith('/admin/observability');
    if (key === 'admin') return path.startsWith('/admin') && !path.startsWith('/admin/observability');
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
    label: 'User',
    initials: 'U'
  };

  function normalizeUser(input: unknown): ViewUser {
    let label = 'User';

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
      initials: initialsFromLabel(label, 'U')
    };
  }

  // 🔁 Réactivité Svelte
  $: viewUser = normalizeUser(user);
  $: hasAlerts = Number(alertsCount ?? 0) > 0;
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
        Dashboard
      </a>

      {#if canSeeStorageRoots}
        <a
          href="/storage-roots"
          class="nav-item {isActive('storageRoots') ? 'active' : ''}"
        >
          Storage Roots
        </a>
      {/if}

      <a
        href="/access-requests"
        class="nav-item {isActive('requests') ? 'active' : ''}"
      >
        Requests
      </a>

      {#if canSeeObservability}
        <button
          type="button"
          class="nav-item {isActive('observability') ? 'active' : ''}"
          on:click={() => openMega('observability')}
        >
          Observability
        </button>
      {/if}

      {#if canSeeAdmin}
        <button
          type="button"
          class="nav-item {isActive('admin') ? 'active' : ''}"
          on:click={() => openMega('admin')}
        >
          Admin
        </button>
      {/if}
    </div>
  </div>

  <!-- RIGHT -->
  <div class="topbar-right">
    <div class="user-menu-wrapper">
      <a href="/access-requests?status=pending" class="topbar-alert-btn" aria-label="Notifications">
        <i class="bi bi-bell" aria-hidden="true"></i>
        {#if hasAlerts}
          <span class="topbar-alert-badge" aria-label={`${alertsCount} alertes`}>{alertsCount > 99 ? '99+' : alertsCount}</span>
        {/if}
      </a>

      <div class="topbar-user-chip" aria-label={`Signed-in user ${viewUser.label}`}>
        <span class="topbar-user-avatar">{viewUser.initials}</span>
        <span class="topbar-user-name">{viewUser.label}</span>
      </div>

      <form method="POST" action="/logout">
        <button type="submit" class="logout-btn">
        <i class="bi bi-box-arrow-right" aria-hidden="true"></i>
        Logout
        </button>
      </form>
    </div>
  </div>
</nav>
