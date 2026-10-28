<script lang="ts">
  import { t } from '$lib/i18n';
  import { enhance } from '$app/forms';
  import LanguageSwitcher from '$lib/components/ui/LanguageSwitcher.svelte';

  export let form: { error?: string } | null = {};
  /** Enabled SSO providers (Advanced Settings › Infrastructure › Keycloak) */
  export let ssoProviders: { id: number; label: string }[] = [];
  /** Page to open after the sign-in */
  export let redirectTo: string | null = null;

  let showPassword = false;
  let loading = false;

  function togglePassword() {
    showPassword = !showPassword;
  }
</script>

<div class="login-page">
  <div class="login-lang">
    <LanguageSwitcher />
  </div>
  <div class="login-card">
    <div class="login-card-inner">

      <!-- BRAND -->
      <h1 class="login-brand">BornToShare</h1>

      <h2 class="login-title">{t('Sign in')}</h2>

      <!-- ========================= -->
      <!-- SSO / ORGANIZATION (PRIMARY) -->
      <!-- ========================= -->
      {#each ssoProviders as provider (provider.id)}
        <a class="login-submit login-sso" href={`/sso/start/${provider.id}${redirectTo ? `?redirect=${encodeURIComponent(redirectTo)}` : ''}`}>
          <span class="sso-text">
            <strong>{ssoProviders.length === 1 ? t('Sign in with your organization') : provider.label}</strong>
            <span class="sso-sub">{ssoProviders.length === 1 ? provider.label : t('Single sign-on')}</span>
          </span>
        </a>
      {/each}

      {#if ssoProviders.length}
        <!-- SEPARATOR -->
        <div class="login-divider"></div>
      {/if}

      <!-- ========================= -->
      <!-- LOCAL LOGIN (FALLBACK) -->
      <!-- ========================= -->
      <form
        class="login-form login-form--local"
        method="POST"
        autocomplete="off"
        use:enhance={() => {
          loading = true;
          return async ({ update }) => {
            try {
              // The public layout shows the toast returned by the action
              await update();
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
            placeholder={t('Username')}
            autocomplete="username"
            required
          />
        </div>

        <div class="form-group password-group">
          <input
            type={showPassword ? 'text' : 'password'}
            class="login-input"
            name="password"
            placeholder={t('Password')}
            autocomplete="current-password"
            required
          />

          <button
            type="button"
            class="toggle-password"
            on:click={togglePassword}
            aria-label={showPassword ? t('Hide password') : t('Show password')}
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
          {#if loading} {t('Signing in…')} {:else} {t('Sign in locally')} {/if}
        </button>
      </form>

    </div>
  </div>
</div>

<style>
  .login-sso {
    display: flex;
    align-items: center;
    justify-content: center;
    text-decoration: none;
    margin-bottom: 10px;
  }

  .login-lang {
    position: fixed;
    top: calc(20px + env(safe-area-inset-top, 0px));
    right: 24px;
    z-index: 2;
  }
</style>
