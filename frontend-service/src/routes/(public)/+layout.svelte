<script lang="ts">
  import { untrack } from 'svelte';

  import { t } from '$lib/i18n';
  // Global styles for public routes (/login, /logout, ...)
  import '@fontsource-variable/geist';
  import '@fontsource-variable/geist-mono';
  import '$lib/styles/tokens.css';
  import '$lib/styles/bootstrap-subset.css';
  import '$lib/styles/bootstrap-icons.min.css';
  import '$lib/styles/modals.css';
  import '$lib/styles/app.css';
  import '$lib/styles/buttons.css';

  import TopProgress from '$lib/components/ui/TopProgress.svelte';
  import Toaster from '$lib/components/ui/Toaster.svelte';
  import { page } from '$app/stores';
  import { toast, type ToastType } from '$lib/stores/toast';
  import { browser } from '$app/environment';
  import { bootstrapFrontendCore } from '$lib/bootstrap.client';
  interface Props {
    children?: import('svelte').Snippet;
  }

  let { children }: Props = $props();

  bootstrapFrontendCore();

  // ==================================================
  // Toast mapping (?toast=xxx dans l’URL)
  // ==================================================
  const toastMap: Record<
    string,
    { type: 'success' | 'error' | 'warning' | 'info'; message: string }
  > = {
    saved: { type: 'success', message: t('Changes saved.') },
    created: { type: 'success', message: t('Creation successful.') },
    deleted: { type: 'success', message: t('Deletion successful.') },
    forbidden: { type: 'error', message: t('Action not authorized.') },
    error: { type: 'error', message: t('An error occurred.') },
    session_expired: {
      type: 'warning',
      message: t('Your session has expired. Please sign in again.')
    }
  };

  let lastUrlToastKey = $state<string | null>(null);
  let lastFormToastKey = $state<string | null>(null);

  // ==================================================
  // Toast via URL (?toast=xxx)
  // 👉 CLIENT ONLY (history)
  // ==================================================
  $effect.pre(() => {
    if (browser) {
      const key = $page.url.searchParams.get('toast');

      if (key && key !== lastUrlToastKey) {
        lastUrlToastKey = key;

        const entry = toastMap[key] ?? {
          type: 'info',
          message: key
        };

        untrack(() => toast.show(entry.type, entry.message));

        // Nettoyage URL (CSR uniquement)
        const url = new URL($page.url);
        url.searchParams.delete('toast');
        history.replaceState(history.state, '', url);
      }
    }
  });

  // ==================================================
  // Toast via form actions (fail / success)
  // (SSR compatible)
  // ==================================================
  $effect.pre(() => {
    const ft = ($page.form as { toast?: { message?: string; type?: ToastType; duration?: number } } | null)?.toast;

    if (ft?.message) {
      const key = `${ft.type ?? 'error'}:${ft.message}`;

      if (key !== lastFormToastKey) {
        lastFormToastKey = key;

        untrack(() => toast.show(
          ft.type ?? 'error',
          // Action messages are English: translate them for display
          t(ft.message),
          ft.duration ?? 3500
        ));
      }
    }
  });
</script>

<!-- Layout minimal pour les pages publiques (auth) -->
{@render children?.()}

<Toaster />
<TopProgress />
