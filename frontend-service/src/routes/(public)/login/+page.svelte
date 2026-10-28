<script lang="ts">
  import { t } from '$lib/i18n';

  import LoginForm from '$lib/components/auth/LoginForm.svelte';
  import ErrorNotice from '$lib/components/ui/ErrorNotice.svelte';

  import { notifyError, toAppError, type AppError } from '$lib/errors';
  import { logAppError } from '$lib/logging';

  export let data: {
    providers?: unknown;
    form?: Record<string, unknown>;
    ssoProviders?: { id: number; label: string }[];
    ssoError?: string | null;
    redirectTo?: string | null;
  };

  // Error normalisée pour affichage inline
  let pageError: AppError | null = null;

  /**
   * SvelteKit expose les failures d’actions via data.form
   * On les transforme UNE fois en UiError
   */
  // Refused SSO sign-in (back from Keycloak): English message from the server, shown once
  let ssoShown = false;
  $: if (data?.ssoError && !ssoShown) {
    ssoShown = true;
    const appError = toAppError(t(String(data.ssoError)), { source: 'auth' });
    pageError = appError;
    notifyError(appError);
  }

  $: if (data?.form?.error) {
    // The server action returns English messages: translate them for display
    const appError = toAppError(t(String(data.form.error)), { source: 'auth' });
    pageError = appError;
    logAppError(appError, { action: 'login.page.form_error' });
    notifyError(appError);
  } else if (!data?.ssoError) {
    pageError = null;
  }
</script>

<svelte:head>
  <title>{t('Sign in')} · BornToShare</title>
</svelte:head>

<LoginForm form={data.form ?? {}} ssoProviders={data.ssoProviders ?? []} redirectTo={data.redirectTo ?? null} />

<!-- Persistent error under the form (optional but recommended) -->
<ErrorNotice error={pageError} />
