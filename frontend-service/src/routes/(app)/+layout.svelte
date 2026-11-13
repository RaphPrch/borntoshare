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
  import { invalidate, onNavigate } from "$app/navigation";
  import { onDestroy, onMount } from "svelte";
  import { connectLive, live, onLiveChange } from "$lib/stores/live";
  import TasksDock from "$lib/components/layout/TasksDock.svelte";
  import UnsavedChangesDialog from "$lib/components/ui/UnsavedChangesDialog.svelte";
  import { unsavedPrompt } from "$lib/utils/unsaved";
  import { installCopyOnClick } from "$lib/utils/copy-on-click";
  import { reducedMotion } from "$lib/utils/motion";
  import { pageTitle } from "$lib/utils/page-title";
  import { t } from "$lib/i18n";

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
      features?: string[];
    };
    theme: string;
  };

  bootstrapFrontendCore();

  // Live updates (/live): badges, bell, tasks; the pages whose data moved reload it themselves
  const stops: Array<() => void> = [];
  onMount(() => {
    stops.push(installCopyOnClick());
    stops.push(connectLive());
    stops.push(onLiveChange((s) => s.requestsStamp, () => void invalidate("b2s:requests")));
    stops.push(onLiveChange((s) => s.alertsStamp, () => void invalidate("b2s:alerts")));
  });
  onDestroy(() => stops.splice(0).forEach((stop) => stop()));

  // Page change between sections (Folders → Servers…): the main area cross-fades (View Transitions).
  // Within a section (another folder, ?selected=…) the workspace animates its own content instead.
  const section = (path: string) => {
    const parts = path.split("/").filter(Boolean);
    return parts.slice(0, parts[0] === "admin" ? 2 : 1).join("/");
  };
  onNavigate((navigation) => {
    if (typeof document === "undefined" || !("startViewTransition" in document) || reducedMotion()) return;
    const from = navigation.from?.url.pathname ?? "";
    const to = navigation.to?.url.pathname ?? "";
    if (!to || section(from) === section(to)) return;
    return new Promise<void>((resolve) => {
      (document as Document & { startViewTransition: (run: () => Promise<void>) => unknown }).startViewTransition(async () => {
        resolve();
        await navigation.complete;
      });
    });
  });
</script>

<svelte:head>
  <title>{pageTitle($page.url.pathname, $live.pending ?? Number(data.topbarAlertsCount ?? 0))}</title>
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

{#if data.navigation?.canSeeAdmin}<TasksDock />{/if}
<UnsavedChangesDialog open={$unsavedPrompt.open} impact={t("The edits made on this page will be lost.")}
  onKeepEditing={() => unsavedPrompt.set({ open: false, discard: null })} onDiscard={() => $unsavedPrompt.discard?.()} />
<SessionIdleBanner />
<Toaster />
<TopProgress />

<style>
  .b2s-banner { display: flex; align-items: center; gap: 10px; margin: 16px 28px 0; padding: 10px 16px; border-radius: var(--b2s-radius-md); font-size: var(--b2s-fs-sm); font-weight: 500; }
  .b2s-banner.is-info { background: var(--b2s-color-info-soft); color: var(--b2s-color-info-strong); }
  .b2s-banner.is-warning { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }
  .b2s-banner.is-danger { background: var(--b2s-color-danger-soft); color: var(--b2s-color-danger-strong); }
</style>
