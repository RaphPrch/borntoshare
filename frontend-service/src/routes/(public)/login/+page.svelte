<script lang="ts">
  import { env } from '$env/dynamic/public';

  import LoginForm from '$lib/components/auth/LoginForm.svelte';
  import ErrorNotice from '$lib/components/common/ErrorNotice.svelte';

  import { notifyError, toAppError, type AppError } from '$lib/core/errors';
  import { logAppError } from '$lib/core/logging';

  export let data: {
    providers?: unknown;
    form?: Record<string, unknown>;
  };

  const idpEnabled = env.PUBLIC_IDP_ENABLED === 'true';

  // Error normalisée pour affichage inline
  let pageError: AppError | null = null;

  /**
   * SvelteKit expose les failures d’actions via data.form
   * On les transforme UNE fois en UiError
   */
  $: if (data?.form?.error) {
    const appError = toAppError(data.form.error, { source: 'auth' });
    pageError = appError;
    logAppError(appError, { action: 'login.page.form_error' });
    notifyError(appError);
  } else {
    pageError = null;
  }
</script>

<LoginForm form={data.form ?? {}} />

<!-- Persistent error under the form (optional but recommended) -->
<ErrorNotice error={pageError} />

{#if idpEnabled}
  <div class="b2s-login-divider">
    <span class="line"></span>
    <span class="label">OR</span>
    <span class="line"></span>
  </div>

  <button
    class="b2s-org-btn"
    type="button"
    aria-label="Sign in with your organization"
  >
    <span class="b2s-org-ico" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none">
        <path
          d="M4 4h7v7H4V4Zm9 0h7v7h-7V4ZM4 13h7v7H4v-7Zm9 0h7v7h-7v-7Z"
          stroke="currentColor"
          stroke-width="1.6"
        />
      </svg>
    </span>
    <span class="b2s-org-text">Sign in with your organization</span>
  </button>
{/if}
