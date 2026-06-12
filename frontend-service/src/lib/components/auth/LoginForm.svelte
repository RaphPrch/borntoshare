<script lang="ts">
  import { enhance } from '$app/forms';
  import { toast } from '$lib/utils/toast';

  export let form: unknown = {};

  let showPassword = false;
  let loading = false;

  function togglePassword() {
    showPassword = !showPassword;
  }
</script>

<div class="login-page">
  <div class="login-card">
    <div class="login-card-inner">

      <!-- BRAND -->
      <h1 class="login-brand">BornToShare</h1>

      <h2 class="login-title">Sign in</h2>

      <!-- ========================= -->
      <!-- SSO / ORGANIZATION (PRIMARY) -->
      <!-- ========================= -->
      <form
        class="login-form"
        method="POST"
        action="?/keycloak"
        use:enhance={() => {
          loading = true;
          return async ({ update }) => {
            try {
              await update();
            } finally {
              loading = false;
            }
          };
        }}
      >
        <button
          type="submit"
          class="login-submit"
          disabled={loading}
        >
          <span class="sso-text">
            <strong>Sign in with your organization</strong>
            <span class="sso-sub">
              Enterprise SSO · Active Directory · Keycloak
            </span>
          </span>
        </button>
      </form>

      <!-- SEPARATOR -->
      <div class="login-divider"></div>

      <!-- ========================= -->
      <!-- LOCAL LOGIN (FALLBACK) -->
      <!-- ========================= -->
      <form
        class="login-form login-form--local"
        method="POST"
        autocomplete="off"
        use:enhance={() => {
          loading = true;
          return async ({ result, update }) => {
            try {
              await update();
              const data =
                (result.type === 'failure' || result.type === 'success')
                  ? (result.data as Record<string, unknown> | undefined)
                  : undefined;

              const toastPayload = data?.toast as
                | { type?: string; message?: string; duration?: number }
                | undefined;
              const message =
                toastPayload?.message ?? (data?.error as string | undefined);

              if (message) {
                const type = toastPayload?.type === 'success' ? 'success' : 'error';
                toast.show(type, message, toastPayload?.duration ?? 4000);
              }
            } finally {
              loading = false;
            }
          };
        }}
      >
        <input type="hidden" name="provider" value="local" />

        <div class="form-group">
          <input
            type="text"
            class="login-input"
            name="username"
            placeholder="Username"
            autocomplete="username"
            required
          />
        </div>

        <div class="form-group password-group">
          <input
            type={showPassword ? 'text' : 'password'}
            class="login-input"
            name="password"
            placeholder="Password"
            autocomplete="current-password"
            required
          />

          <button
            type="button"
            class="toggle-password"
            on:click={togglePassword}
            aria-label={showPassword ? 'Hide password' : 'Show password'}
          >
            <i
              class="bi {showPassword ? 'bi-eye-slash' : 'bi-eye'}"
              aria-hidden="true"
            ></i>
          </button>
        </div>

        {#if form?.error}
          <p class="error-message" role="alert">{form.error}</p>
        {/if}

        <button
          type="submit"
          class="login-submit"
          disabled={loading}
        >
          {#if loading} Signing in… {:else} Sign in locally {/if}
        </button>
      </form>

    </div>
  </div>
</div>
