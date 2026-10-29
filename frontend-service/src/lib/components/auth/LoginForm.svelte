<script lang="ts">
  import { t } from '$lib/i18n';
  import { enhance } from '$app/forms';
  import LanguageSwitcher from '$lib/components/ui/LanguageSwitcher.svelte';

  export let form: { error?: string } | null = {};
  /** Enabled SSO providers (Advanced Settings › Infrastructure › Keycloak) */
  export let ssoProviders: { id: number; label: string }[] = [];
  /** Page to open after the sign-in */
  export let redirectTo: string | null = null;
  /** Enabled sign-in providers: a directory adds the « Directory » tab */
  export let providers: string[] = [];

  let showPassword = false;
  let loading = false;

  $: hasDirectory = providers.some((name) => name !== 'local');
  let mode: 'directory' | 'local' | null = null;
  $: activeMode = hasDirectory ? (mode ?? 'directory') : 'local';

  function togglePassword() {
    showPassword = !showPassword;
  }

  // Illustration of the product, not real data
  $: lanes = [
    { person: 'Alice Bernard', via: t('approved request'), group: 'B2S_FINANCE_RX', folder: 'Finance', level: t('read'), tone: 'read' },
    { person: 'Julien Durand', via: t('approved request'), group: 'B2S_FINANCE_RW', folder: 'Finance', level: t('modify'), tone: 'write' },
    { person: 'Sophie Moreau', via: t('ends in 5 days'), group: 'B2S_LEGAL_RX', folder: t('Legal'), level: t('read'), tone: 'read' }
  ];
</script>

<div class="lg">
  <section class="lg__hero">
    <div class="lg__brand"><span class="lg__logo" aria-hidden="true">B</span><strong>BornToShare</strong></div>

    <div class="lg__pitch">
      <p class="lg__headline">{t('Who can access what.')}<br /><mark>{t('And why.')}</mark></p>
      <div class="lg__lanes" aria-hidden="true">
        {#each lanes as lane}
          <div class={`lg__lane is-${lane.tone}`}>
            <div class="lg__node"><strong>{lane.person}</strong><small>{lane.via}</small></div>
            <div class="lg__wire"></div>
            <div class="lg__node"><code>{lane.group}</code><small>{t('Active Directory group')}</small></div>
            <div class="lg__wire"></div>
            <div class="lg__node"><strong>{lane.folder}</strong><small>{lane.level}</small></div>
          </div>
        {/each}
      </div>
    </div>

    <p class="lg__foot">{t('Access to shared folders, governed and checked on the file server.')}</p>
  </section>

  <main class="lg__panel">
    <div class="lg__lang"><LanguageSwitcher tone="light" /></div>

    <div>
      <h1>{t('Sign in')}</h1>
      <p class="lg__hint">{activeMode === 'directory' ? t('With your company account.') : t('Reserved for platform administration.')}</p>
    </div>

    {#if hasDirectory}
      <div class="lg__seg" role="group" aria-label={t('Account type')}>
        <button type="button" class:on={activeMode === 'directory'} aria-pressed={activeMode === 'directory'} on:click={() => (mode = 'directory')}>{t('Directory')}</button>
        <button type="button" class:on={activeMode === 'local'} aria-pressed={activeMode === 'local'} on:click={() => (mode = 'local')}>{t('Local account')}</button>
      </div>
    {/if}

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
      <input type="hidden" name="provider" value={activeMode === 'directory' ? 'ad' : 'local'} />

      <label class="lg__field">
        <span>{activeMode === 'directory' ? t('Username or email') : t('Username')}</span>
        <input type="text" name="username" autocomplete="username" required />
      </label>

      <label class="lg__field">
        <span>{t('Password')}</span>
        <span class="lg__password">
          <input type={showPassword ? 'text' : 'password'} name="password" autocomplete="current-password" required />
          <button type="button" on:click={togglePassword} aria-label={showPassword ? t('Hide password') : t('Show password')}>
            <i class="bi {showPassword ? 'bi-eye-slash' : 'bi-eye'}" aria-hidden="true"></i>
          </button>
        </span>
      </label>

      {#if form?.error}
        <p class="lg__error" role="alert">{form.error}</p>
      {/if}

      <button type="submit" class="lg__submit" disabled={loading}>
        {#if loading}{t('Signing in…')}{:else}{t('Sign in')}{/if}
      </button>
    </form>

    {#if ssoProviders.length}
      <div class="lg__or"><span>{t('or')}</span></div>
      {#each ssoProviders as provider (provider.id)}
        <a class="lg__sso" href={`/sso/start/${provider.id}${redirectTo ? `?redirect=${encodeURIComponent(redirectTo)}` : ''}`}>
          {t('Continue with {label}', { label: provider.label })}
        </a>
      {/each}
    {/if}

    <slot />
  </main>
</div>

<style>
  .lg {
    --lg-bg: #f3f4f7;
    --lg-surface: #fff;
    --lg-line: #e1e4ea;
    --lg-line2: #cdd2db;
    --lg-text: #0e1218;
    --lg-muted: #596273;
    --lg-accent: #b6f24a;
    --lg-read: #1f5fd0;
    --lg-write: #a85a00;
    --lg-shadow: 0 1px 2px rgba(14, 18, 24, 0.05), 0 8px 24px rgba(14, 18, 24, 0.06);
    min-height: 100vh;
    display: flex;
    background: var(--lg-bg);
    color: var(--lg-text);
    font-family: 'Geist Variable', var(--b2s-font-sans);
    font-size: 15px;
    line-height: 1.45;
  }

  .lg__hero {
    flex: 999 1 560px;
    min-width: 0;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    gap: 44px;
    padding: 44px clamp(24px, 5vw, 72px);
  }

  .lg__brand {
    display: flex;
    align-items: center;
    gap: 12px;
    font-size: 18px;
  }

  .lg__brand strong {
    font-weight: 600;
    letter-spacing: -0.01em;
  }

  .lg__logo {
    width: 40px;
    height: 40px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 12px;
    background: var(--lg-accent);
    color: #10140a;
    font-weight: 700;
  }

  .lg__pitch {
    display: grid;
    gap: 40px;
  }

  .lg__headline {
    margin: 0;
    font-size: clamp(44px, 6vw, 84px);
    font-weight: 600;
    line-height: 1.14;
    letter-spacing: -0.04em;
  }

  .lg__headline mark {
    padding: 0 0.14em;
    border-radius: 0.14em;
    background: var(--lg-accent);
    color: inherit;
    -webkit-box-decoration-break: clone;
    box-decoration-break: clone;
  }

  .lg__lanes {
    display: grid;
    gap: 12px;
  }

  .lg__lane {
    --flow: var(--lg-read);
    display: grid;
    grid-template-columns: minmax(0, 1fr) 40px minmax(0, 1.3fr) 40px minmax(0, 1fr);
    align-items: center;
  }

  .lg__lane.is-write {
    --flow: var(--lg-write);
  }

  .lg__node {
    min-width: 0;
    padding: 12px 14px;
    border: 1px solid var(--lg-line);
    border-radius: 14px;
    background: var(--lg-surface);
    box-shadow: var(--lg-shadow);
    font-size: 14px;
  }

  .lg__node strong {
    display: block;
    font-weight: 600;
  }

  .lg__node code {
    display: block;
    color: inherit;
    font-family: 'Geist Mono Variable', var(--b2s-font-mono);
    font-size: 12px;
    overflow-wrap: anywhere;
  }

  .lg__node small {
    display: block;
    color: var(--lg-muted);
    font-size: 12px;
  }

  .lg__wire {
    position: relative;
    height: 2px;
    overflow: hidden;
    background: var(--lg-line2);
  }

  .lg__wire::after {
    content: '';
    position: absolute;
    top: 0;
    bottom: 0;
    width: 40%;
    background: var(--flow);
    animation: lg-flow 2.2s linear infinite;
  }

  @keyframes lg-flow {
    from { left: -40%; }
    to { left: 100%; }
  }

  @media (prefers-reduced-motion: reduce) {
    .lg__wire::after {
      left: 30%;
      animation: none;
    }
  }

  .lg__foot {
    margin: 0;
    color: var(--lg-muted);
    font-size: 12px;
  }

  .lg__panel {
    position: relative;
    flex: 1 1 420px;
    max-width: 520px;
    margin: 24px 24px 24px auto;
    padding: 40px clamp(24px, 4vw, 48px);
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: 22px;
    border: 1px solid var(--lg-line);
    border-radius: 24px;
    background: var(--lg-surface);
    box-shadow: var(--lg-shadow);
  }

  .lg__lang {
    position: absolute;
    top: 20px;
    right: 20px;
  }

  h1 {
    margin: 0;
    font-size: 32px;
    font-weight: 600;
    letter-spacing: -0.025em;
  }

  .lg__hint {
    margin: 6px 0 0;
    color: var(--lg-muted);
  }

  .lg__seg {
    display: flex;
    gap: 3px;
    padding: 3px;
    border-radius: 12px;
    background: #e9ebf0;
  }

  .lg__seg button {
    flex: 1;
    min-height: 40px;
    border: 0;
    border-radius: 9px;
    background: transparent;
    color: var(--lg-muted);
    font: inherit;
    font-weight: 500;
    cursor: pointer;
  }

  .lg__seg button.on {
    background: var(--lg-surface);
    color: var(--lg-text);
    box-shadow: 0 1px 2px rgba(14, 18, 24, 0.12);
  }

  .lg__form {
    display: grid;
    gap: 14px;
  }

  .lg__field {
    display: grid;
    gap: 7px;
    margin: 0;
    font-size: 13px;
    font-weight: 500;
  }

  .lg__field input {
    width: 100%;
    min-height: 52px;
    padding: 0 16px;
    border: 1px solid var(--lg-line2);
    border-radius: 14px;
    outline: 0;
    background: var(--lg-surface);
    color: var(--lg-text);
    font: inherit;
    font-size: 16px;
    font-weight: 400;
    box-sizing: border-box;
  }

  .lg__field input:focus {
    border-color: var(--lg-text);
    box-shadow: 0 0 0 1px var(--lg-text);
  }

  .lg__password {
    position: relative;
    display: block;
  }

  .lg__password input {
    padding-right: 52px;
  }

  .lg__password button {
    position: absolute;
    top: 4px;
    right: 4px;
    width: 44px;
    height: 44px;
    border: 0;
    border-radius: 10px;
    background: transparent;
    color: var(--lg-muted);
    cursor: pointer;
  }

  .lg__error {
    margin: 0;
    color: var(--b2s-color-danger-strong);
  }

  .lg__submit,
  .lg__sso {
    min-height: 52px;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0 18px;
    border-radius: 14px;
    font: inherit;
    font-weight: 600;
    text-align: center;
    text-decoration: none;
    cursor: pointer;
  }

  .lg__submit {
    border: 1px solid #9ad632;
    background: var(--lg-accent);
    color: #10140a;
  }

  .lg__submit:hover {
    background: #abea3c;
  }

  .lg__submit:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .lg__sso {
    border: 1px solid var(--lg-line2);
    background: var(--lg-surface);
    color: var(--lg-text);
    font-weight: 500;
  }

  .lg__sso:hover {
    background: #f6f7f9;
    color: var(--lg-text);
  }

  .lg__or {
    display: flex;
    align-items: center;
    gap: 12px;
    color: var(--lg-muted);
    font-size: 12px;
  }

  .lg__or::before,
  .lg__or::after {
    content: '';
    flex: 1;
    height: 1px;
    background: var(--lg-line);
  }

</style>
