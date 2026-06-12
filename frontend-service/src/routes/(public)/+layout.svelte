<script lang="ts">
  // Global styles for public routes (/login, /logout, ...)
  import '$lib/styles/tokens.css';
  import '$lib/styles/bootstrap.min.css';
  import '$lib/styles/bootstrap-icons.min.css';
  import '$lib/styles/modals.css';
  import '$lib/styles/app.css';

  import TopProgress from '$lib/components/ui/TopProgress.svelte';
  import Toaster from '$lib/components/ui/Toaster.svelte';
  import { page } from '$app/stores';
  import { toast } from '$lib/utils/toast';
  import { browser } from '$app/environment';
  import { bootstrapFrontendCore } from '$lib/core/bootstrap.client';

  bootstrapFrontendCore();

  // ==================================================
  // Toast mapping (?toast=xxx dans l’URL)
  // ==================================================
  const toastMap: Record<
    string,
    { type: 'success' | 'error' | 'warning' | 'info'; message: string }
  > = {
    saved: { type: 'success', message: 'Changes saved.' },
    created: { type: 'success', message: 'Creation successful.' },
    deleted: { type: 'success', message: 'Deletion successful.' },
    forbidden: { type: 'error', message: 'Action not authorized.' },
    error: { type: 'error', message: 'An error occurred.' },
    session_expired: {
      type: 'warning',
      message: 'Your session has expired. Please sign in again.'
    }
  };

  let lastUrlToastKey: string | null = null;
  let lastFormToastKey: string | null = null;

  // ==================================================
  // Toast via URL (?toast=xxx)
  // 👉 CLIENT ONLY (history)
  // ==================================================
  $: if (browser) {
    const key = $page.url.searchParams.get('toast');

    if (key && key !== lastUrlToastKey) {
      lastUrlToastKey = key;

      const toast = toastMap[key] ?? {
        type: 'info',
        message: key
      };

      toast.show(toast.type, toast.message);

      // Nettoyage URL (CSR uniquement)
      const url = new URL($page.url);
      url.searchParams.delete('toast');
      history.replaceState(history.state, '', url);
    }
  }

  // ==================================================
  // Toast via form actions (fail / success)
  // (SSR compatible)
  // ==================================================
  $: {
    const ft = ($page as unknown).form?.toast;

    if (ft?.message) {
      const key = `${ft.type ?? 'error'}:${ft.message}`;

      if (key !== lastFormToastKey) {
        lastFormToastKey = key;

        toast.show(
          ft.type ?? 'error',
          ft.message,
          ft.duration ?? 3500
        );
      }
    }
  }
</script>

<!-- Layout minimal pour les pages publiques (auth) -->
<slot />

<Toaster />
<TopProgress />
