<script lang="ts">
  // =========================================================
  // BornToShare – Global App Layout (V1.6 – STABLE)
  // =========================================================

  // =========================================================
  // BornToShare – Global CSS (single entry-point)
  // Goal: 1 tokens file + 1 global stylesheet, fewer imports.
  // =========================================================

  // 1️⃣ Design tokens (single source of truth)
  import "$lib/styles/tokens.css";

  // 2️⃣ Bootstrap (kept for grid/utilities only)
  import "$lib/styles/bootstrap.min.css";
  import "$lib/styles/bootstrap-icons.min.css";
  import "$lib/styles/modals.css";

  // 3️⃣ BornToShare global stylesheet (merged)
  import "$lib/styles/layout.css";
  import "$lib/styles/app.css";
  import "$lib/styles/storage-roots.css";

  import { page } from "$app/stores";

  import Toaster from "$lib/components/ui/Toaster.svelte";
  import TopProgress from "$lib/components/ui/TopProgress.svelte";
  import Topbar from "$lib/components/layout/Topbar.svelte";
  import MegaMenu from "$lib/components/layout/MegaMenu.svelte";
  import { bootstrapFrontendCore } from "$lib/core/bootstrap.client";

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
    topbarAlertsCount?: number;
    navigation?: {
      canSeeStorageRoots?: boolean;
      canSeeObservability?: boolean;
      canSeeAdmin?: boolean;
      guardianRootIds?: number[];
    };
    theme: string;
  };

  let activeMega: import('$lib/components/mega-config').MegaMenuKey | null = null;

  bootstrapFrontendCore();

  // Reset mega-menu on navigation
  $: $page.url.pathname, activeMega = null;
</script>

<div class="b2s-app-root">
  <Topbar
    bind:activeMega
    user={data.me}
    permissions={data.navigation}
    alertsCount={Number(data.topbarAlertsCount ?? 0)}
    currentPath={$page.url.pathname}
  />

  <MegaMenu {activeMega} permissions={data.navigation} close={() => (activeMega = null)} />

  <main class="b2s-app-main">
    <slot />
  </main>
</div>

<Toaster />
<TopProgress />
