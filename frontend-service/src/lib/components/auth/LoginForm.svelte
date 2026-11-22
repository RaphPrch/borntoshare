<script lang="ts">
  import { t } from '$lib/i18n';
  import { enhance } from '$app/forms';
  import LanguageSwitcher from '$lib/components/ui/LanguageSwitcher.svelte';

  interface Props {
    form?: { error?: string } | null;
    /** Enabled SSO providers (Advanced Settings › Infrastructure › Keycloak) */
    ssoProviders?: { id: number; label: string }[];
    /** Page to open after the sign-in */
    redirectTo?: string | null;
    children?: import('svelte').Snippet;
  }

  let {
    form = {},
    ssoProviders = [],
    redirectTo = null,
    children
  }: Props = $props();

  let showPassword = $state(false);
  let loading = $state(false);

  function togglePassword() {
    showPassword = !showPassword;
  }

  const features = [
    { icon: 'bi-send-check', title: 'Request and approve', text: 'Users request access to a folder, its guardians decide, every decision is traced.' },
    { icon: 'bi-people', title: 'Active Directory and NTFS handled for you', text: 'AD groups, memberships and permissions are applied on the file server, then checked.' },
    { icon: 'bi-shield-check', title: 'Always know who has access', text: 'Permissions set outside the process, ending accesses and unreachable servers are reported.' },
    { icon: 'bi-bar-chart', title: 'Measure and tidy shares (5S)', text: 'Scan volumes, find duplicates and stale data, track storage hygiene over time.' }
  ];
</script>

<div class="lg">
  <section class="lg__hero">
    <div class="lg__pitch">
      <p class="lg__headline">{t('Who accesses what.')}<br />{t('What is in there.')}<br /><mark>{t('And why.')}</mark></p>
      <p class="lg__lead">{t('BornToShare governs your shared folders: who may access them, from the request to the permissions on the file server, and what they hold, with volumes, duplicates and dormant data measured over time.')}</p>
      <ul class="lg__features">
        {#each features as feature}
          <li>
            <i class={`bi ${feature.icon}`} aria-hidden="true"></i>
            <span><strong>{t(feature.title)}</strong>{t(feature.text)}</span>
          </li>
        {/each}
      </ul>
    </div>

    <p class="lg__trust"><i class="bi bi-shield-check" aria-hidden="true"></i>{t('Secure and compliant')}</p>
  </section>

  <main class="lg__panel">
    <div class="lg__lang"><LanguageSwitcher tone="light" /></div>

    <div>
      <h1>{t('Sign in')}</h1>
      <p class="lg__hint">{t('With your company account.')}</p>
    </div>

    <form
      class="lg__form"
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
      <label class="lg__field">
        <span>{t('Username or email')}</span>
        <span class="lg__control">
          <i class="bi bi-person" aria-hidden="true"></i>
          <input type="text" name="username" autocomplete="username" placeholder={t('Your username')} aria-describedby="lg-login-help" required />
        </span>
        <small class="lg__help" id="lg-login-help">{t('Email address or DOMAIN\\user for a directory account, user name for a local account.')}</small>
      </label>

      <label class="lg__field">
        <span>{t('Password')}</span>
        <span class="lg__control lg__password">
          <i class="bi bi-lock" aria-hidden="true"></i>
          <input type={showPassword ? 'text' : 'password'} name="password" autocomplete="current-password" placeholder={t('Your password')} required />
          <button type="button" onclick={togglePassword} aria-label={showPassword ? t('Hide password') : t('Show password')}>
            <i class="bi {showPassword ? 'bi-eye-slash' : 'bi-eye'}" aria-hidden="true"></i>
          </button>
        </span>
      </label>

      {#if form?.error}
        <p class="lg__error" role="alert">{form.error}</p>
      {/if}

      <button type="submit" class="lg__submit" disabled={loading}>
        {#if loading}{t('Signing in…')}{:else}<i class="bi bi-box-arrow-in-right" aria-hidden="true"></i>{t('Sign in')}{/if}
      </button>
    </form>

    {#if ssoProviders.length}
      <div class="lg__or"><span>{t('or')}</span></div>
      {#each ssoProviders as provider (provider.id)}
        <a class="lg__sso" href={`/sso/start/${provider.id}${redirectTo ? `?redirect=${encodeURIComponent(redirectTo)}` : ''}`} title={provider.label}>
          <i class="bi bi-key" aria-hidden="true"></i>{t('Continue with SSO')}
        </a>
      {/each}
    {/if}

    {@render children?.()}
  </main>
</div>

<style>
  .lg {
    position: relative;
    min-height: 100vh;
    display: flex;
    overflow: hidden;
    /* Two soft teal bands behind the page: the only decoration, no motion */
    background:
      linear-gradient(135deg, transparent 52%, rgba(7, 156, 156, 0.07) 52%, rgba(7, 156, 156, 0.07) 66%, transparent 66%),
      linear-gradient(135deg, transparent 70%, rgba(7, 156, 156, 0.11) 70%, rgba(7, 156, 156, 0.11) 82%, transparent 82%),
      var(--b2s-bg);
    color: var(--b2s-color-text);
    font-family: var(--b2s-font-sans);
    font-size: 15px;
    line-height: 1.45;
  }

  .lg__hero {
    flex: 999 1 560px;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 48px;
    padding: 44px clamp(24px, 5vw, 72px) 32px;
  }

  .lg__pitch {
    margin-block: auto;
    display: grid;
    gap: 28px;
  }

  .lg__headline {
    margin: 0;
    color: var(--b2s-color-heading);
    font-size: clamp(40px, 4.6vw, 66px);
    font-weight: 700;
    line-height: 1.12;
    letter-spacing: -0.04em;
  }

  .lg__headline mark {
    padding: 0 0.16em;
    border-radius: 0.16em;
    background: linear-gradient(90deg, #8fe6c6, var(--b2s-brand));
    color: var(--b2s-topbar-bg);
    -webkit-box-decoration-break: clone;
    box-decoration-break: clone;
  }

  .lg__lead {
    max-width: 640px;
    margin: 0;
    color: var(--b2s-color-text-soft);
    font-size: 20px;
    line-height: 1.45;
    letter-spacing: -0.01em;
  }

  .lg__features {
    display: grid;
    gap: 18px;
    max-width: 640px;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .lg__features li {
    display: flex;
    align-items: flex-start;
    gap: 16px;
  }

  .lg__features i {
    width: 44px;
    height: 44px;
    flex: none;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 12px;
    background: var(--b2s-accent-soft);
    color: var(--b2s-accent);
    font-size: 20px;
  }

  .lg__features strong {
    display: block;
    color: var(--b2s-color-heading);
    font-weight: 600;
  }

  .lg__features span {
    color: var(--b2s-color-text-muted);
  }

  .lg__trust {
    display: flex;
    align-items: center;
    gap: 10px;
    margin: 0;
    color: var(--b2s-accent);
    font-size: 14px;
    font-weight: 500;
  }

  .lg__trust::before {
    content: '';
    width: 40px;
    height: 1px;
    background: var(--b2s-accent-vivid);
  }

  .lg__trust i {
    font-size: 18px;
  }

  .lg__panel {
    position: relative;
    flex: 1 1 420px;
    max-width: 520px;
    align-self: center;
    margin: 24px clamp(24px, 4vw, 64px) 24px auto;
    padding: 48px clamp(24px, 3.5vw, 44px);
    display: flex;
    flex-direction: column;
    gap: 22px;
    border: 1px solid var(--b2s-color-border-soft);
    border-radius: 24px;
    background: var(--b2s-color-surface);
    box-shadow: 0 1px 2px rgba(18, 59, 73, 0.05), 0 24px 48px -12px rgba(18, 59, 73, 0.14);
  }

  .lg__lang {
    position: absolute;
    top: 20px;
    right: 20px;
  }

  h1 {
    margin: 0;
    color: var(--b2s-color-heading);
    font-size: 36px;
    font-weight: 600;
    letter-spacing: -0.025em;
  }

  .lg__hint {
    margin: 6px 0 0;
    color: var(--b2s-color-text-muted);
    font-size: 17px;
  }

  .lg__password button:focus-visible,
  .lg__submit:focus-visible,
  .lg__sso:focus-visible {
    outline: 0;
    box-shadow: var(--b2s-focus-ring);
  }

  .lg__form {
    display: grid;
    gap: 16px;
  }

  .lg__field {
    display: grid;
    gap: 8px;
    margin: 0;
    color: var(--b2s-color-heading);
    font-size: 14px;
    font-weight: 500;
  }

  .lg__help {
    color: var(--b2s-color-text-muted);
    font-size: 12.5px;
    font-weight: 400;
  }

  .lg__control {
    position: relative;
    display: block;
  }

  .lg__control > i {
    position: absolute;
    top: 50%;
    left: 18px;
    transform: translateY(-50%);
    color: var(--b2s-color-text-muted);
    font-size: 18px;
    pointer-events: none;
  }

  .lg__control input {
    width: 100%;
    min-height: 54px;
    padding: 0 16px 0 50px;
    border: 1px solid var(--b2s-color-border);
    border-radius: 14px;
    outline: 0;
    background: var(--b2s-color-surface);
    color: var(--b2s-color-text);
    font: inherit;
    font-size: 16px;
    font-weight: 400;
    box-sizing: border-box;
    transition: border-color var(--b2s-motion-fast) var(--b2s-ease-out), box-shadow var(--b2s-motion-fast) var(--b2s-ease-out);
  }

  .lg__control input::placeholder {
    color: var(--b2s-color-text-faint);
  }

  .lg__control input:focus {
    border-color: var(--b2s-accent-vivid);
    box-shadow: var(--b2s-focus-ring);
  }

  .lg__password input {
    padding-right: 52px;
  }

  .lg__password button {
    position: absolute;
    top: 5px;
    right: 5px;
    width: 44px;
    height: 44px;
    border: 0;
    border-radius: 10px;
    background: transparent;
    color: var(--b2s-color-text-muted);
    cursor: pointer;
  }

  .lg__password button:hover {
    color: var(--b2s-color-heading);
  }

  .lg__error {
    margin: 0;
    color: var(--b2s-color-danger-strong);
  }

  .lg__submit,
  .lg__sso {
    min-height: 54px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    padding: 0 18px;
    border-radius: 14px;
    font: inherit;
    font-weight: 600;
    text-align: center;
    text-decoration: none;
    cursor: pointer;
    transition: background-color var(--b2s-motion-base) var(--b2s-ease-out), border-color var(--b2s-motion-base) var(--b2s-ease-out);
  }

  .lg__submit {
    margin-top: 6px;
    border: 1px solid var(--b2s-accent);
    background: var(--b2s-accent);
    color: var(--b2s-on-accent);
    font-size: 16px;
  }

  .lg__submit i {
    font-size: 18px;
  }

  .lg__submit:hover:not(:disabled) {
    border-color: var(--b2s-accent-strong);
    background: var(--b2s-accent-strong);
  }

  .lg__submit:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .lg__sso {
    border: 1px solid var(--b2s-color-border);
    background: var(--b2s-color-surface);
    color: var(--b2s-color-text);
    font-weight: 500;
  }

  .lg__sso:hover {
    background: var(--b2s-color-surface-soft);
    color: var(--b2s-color-text);
  }

  .lg__or {
    display: flex;
    align-items: center;
    gap: 12px;
    color: var(--b2s-color-text-muted);
    font-size: 12px;
  }

  .lg__or::before,
  .lg__or::after {
    content: '';
    flex: 1;
    height: 1px;
    background: var(--b2s-color-border-soft);
  }
</style>
