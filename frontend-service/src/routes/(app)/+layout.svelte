<script lang="ts">
  // =========================================================
  // BornToShare – Global App Layout (V1.6 – STABLE)
  // =========================================================

  // =========================================================
  // BornToShare – Global CSS (single entry-point)
  // Goal: 1 tokens file + 1 global stylesheet, fewer imports.
  // =========================================================

  // 1️⃣ Design tokens (single source of truth)
  import "@fontsource-variable/geist";
  import "@fontsource-variable/geist-mono";
  import "$lib/styles/tokens.css";

  // 2️⃣ Bootstrap (kept for grid/utilities only)
  import "$lib/styles/bootstrap-subset.css";
  import "$lib/styles/bootstrap-icons.min.css";
  import "$lib/styles/modals.css";

  // 3️⃣ BornToShare global stylesheet (merged)
  import "$lib/styles/layout.css";
  import "$lib/styles/app.css";
  import "$lib/styles/signal.css";
  import "$lib/styles/buttons.css";
  import "$lib/styles/storage-roots.css";

  import { page } from "$app/stores";
  import { pageTitle } from "$lib/utils/page-title";

  import Toaster from "$lib/components/ui/Toaster.svelte";
  import SessionIdleBanner from "$lib/components/layout/SessionIdleBanner.svelte";
  import TopProgress from "$lib/components/ui/TopProgress.svelte";
  import Sidebar from "$lib/components/layout/Sidebar.svelte";
  import { bootstrapFrontendCore } from "$lib/bootstrap.client";

  // ---------------------------------------------------------
  // Data from layout.server.ts
  // ---------------------------------------------------------
  export let data: {
    me: {
      id: number;
      username?: string;
      display_name?: string;
      email?: string;
    };
    banner?: { message?: string; tone?: string } | null;
    topbarAlertsCount?: number;
    topbarCriticalAlerts?: number;
    navigation?: {
      canSeeStorageRoots?: boolean;
      canSeeObservability?: boolean;
      canSeeAdmin?: boolean;
      guardianRootIds?: number[];
    };
    theme: string;
  };

  bootstrapFrontendCore();
</script>

<svelte:head>
  <title>{pageTitle($page.url.pathname, Number(data.topbarAlertsCount ?? 0))}</title>
</svelte:head>

<div class="b2s-app-root">
  <Sidebar
    user={data.me}
    permissions={data.navigation}
    alertsCount={Number(data.topbarAlertsCount ?? 0)}
    criticalAlertsCount={Number(data.topbarCriticalAlerts ?? 0)}
    currentPath={$page.url.pathname}
  />

  <main class="b2s-app-main">
    {#if data.banner}
      <div class="b2s-banner is-{data.banner.tone ?? 'info'}" role="status"><i class="bi bi-megaphone" aria-hidden="true"></i>{data.banner.message}</div>
    {/if}
    <slot />
  </main>
</div>

<SessionIdleBanner />
<Toaster />
<TopProgress />

<style>
  .b2s-banner { display: flex; align-items: center; gap: 10px; margin: 16px 28px 0; padding: 10px 16px; border-radius: var(--b2s-radius-md); font-size: var(--b2s-fs-sm); font-weight: 500; }
  .b2s-banner.is-info { background: var(--b2s-color-info-soft); color: var(--b2s-color-info-strong); }
  .b2s-banner.is-warning { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }
  .b2s-banner.is-danger { background: var(--b2s-color-danger-soft); color: var(--b2s-color-danger-strong); }
</style>
