<script lang="ts">
  import { createEventDispatcher } from 'svelte';

  export let usernameLabel = 'Username';
  export let passwordLabel = 'Password';
  export let usernamePlaceholder = '';
  export let passwordPlaceholder = '';

  export let username: string | null = '';
  export let password: string | null = '';
  export let secret_ref: string | null = '';

  /**
   * identity: keep your existing .field blocks (wizard LDAP)
   * storage: keep your existing grid layout (wizard storage endpoint)
   */
  export let variant: 'identity' | 'storage' | 'generic' = 'generic';

  export let showSecretRef = true;
  export let disablePasswordWhenSecretRef = true;

  const dispatch = createEventDispatcher<{
    usernameBlur: void;
    passwordBlur: void;
    secretRefBlur: void;
  }>();

  let reveal = false;
  $: passwordDisabled = Boolean(disablePasswordWhenSecretRef && (secret_ref ?? '').trim());

  function onBlurUsername() {
    dispatch('usernameBlur');
  }
  function onBlurPassword() {
    dispatch('passwordBlur');
  }
  function onBlurSecretRef() {
    dispatch('secretRefBlur');
  }
</script>

{#if variant === 'identity'}
  <div class="field">
    <label>{usernameLabel}</label>
    <input
      type="text"
      bind:value={username}
      placeholder={usernamePlaceholder}
      on:blur={onBlurUsername}
    />
    <slot name="afterUsername" />
  </div>

  <div class="field">
    <label>{passwordLabel}</label>
    <div class="password-row">
      <input
        type={reveal ? 'text' : 'password'}
        bind:value={password}
        placeholder={passwordPlaceholder}
        disabled={passwordDisabled}
        on:blur={onBlurPassword}
      />
      <button
        class="eye"
        type="button"
        on:click={() => (reveal = !reveal)}
        aria-label={reveal ? 'Hide password' : 'Show password'}
      >
        <i class={`bi ${reveal ? 'bi-eye-slash' : 'bi-eye'}`} aria-hidden="true"></i>
      </button>
    </div>

    {#if showSecretRef}
      <div class="hint">or use an existing secret reference</div>
      <input
        class="secret-ref"
        type="text"
        bind:value={secret_ref}
        placeholder="vault://…"
        on:blur={onBlurSecretRef}
      />
    {/if}

    <slot name="afterPassword" />
  </div>
{:else if variant === 'storage'}
  <div class="se-form-grid se-form-grid--creds">
    <div class="se-form-item">
      <label>{usernameLabel}</label>
      <input
        class="se-input"
        type="text"
        bind:value={username}
        placeholder={usernamePlaceholder}
        on:blur={onBlurUsername}
      />
      <slot name="afterUsername" />
    </div>

    <div class="se-form-item">
      <label>{passwordLabel}</label>
      <div class="se-password">
        <input
          class="se-input"
          type={reveal ? 'text' : 'password'}
          bind:value={password}
          placeholder={passwordPlaceholder}
          disabled={passwordDisabled}
          on:blur={onBlurPassword}
        />
        <button
          class="se-eye"
          type="button"
          on:click={() => (reveal = !reveal)}
          aria-label={reveal ? 'Hide password' : 'Show password'}
        >
          <i class={`bi ${reveal ? 'bi-eye-slash' : 'bi-eye'}`} aria-hidden="true"></i>
        </button>
      </div>

      {#if showSecretRef}
        <small class="se-muted">or existing secret_ref</small>
        <input
          class="se-input"
          type="text"
          bind:value={secret_ref}
          placeholder="vault://…"
          on:blur={onBlurSecretRef}
        />
      {/if}

      <slot name="afterPassword" />
    </div>
  </div>
{:else}
  <div class="b2s-form-grid">
    <div>
      <label>{usernameLabel}</label>
      <input type="text" bind:value={username} placeholder={usernamePlaceholder} on:blur={onBlurUsername} />
      <slot name="afterUsername" />
    </div>

    <div>
      <label>{passwordLabel}</label>
      <div class="password-row">
        <input
          type={reveal ? 'text' : 'password'}
          bind:value={password}
          placeholder={passwordPlaceholder}
          disabled={passwordDisabled}
          on:blur={onBlurPassword}
        />
        <button
          class="eye"
          type="button"
          on:click={() => (reveal = !reveal)}
          aria-label={reveal ? 'Hide password' : 'Show password'}
        >
          <i class={`bi ${reveal ? 'bi-eye-slash' : 'bi-eye'}`} aria-hidden="true"></i>
        </button>
      </div>
      {#if showSecretRef}
        <input type="text" bind:value={secret_ref} placeholder="vault://…" on:blur={onBlurSecretRef} />
      {/if}
      <slot name="afterPassword" />
    </div>
  </div>
{/if}

<style>
  .field {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin-bottom: 12px;
  }

  .field label {
    font-size: 12px;
    font-weight: 800;
    color: #475569;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .field input {
    width: 100%;
    padding: 12px 14px;
    border-radius: 10px;
    border: 1px solid #cbd5e1;
    font-size: 14px;
    font-weight: 600;
    color: #0f172a;
  }

  .field input:focus-visible {
    outline: none;
    border-color: var(--b2s-topbar-bg, #0b1530);
    box-shadow: 0 0 0 4px rgba(11, 21, 48, 0.18);
  }

  .field input:disabled {
    background: #f8fafc;
    color: #64748b;
    cursor: not-allowed;
  }

  .password-row {
    display: flex;
    gap: 8px;
    align-items: center;
  }

  .password-row input {
    flex: 1;
  }

  .eye {
    border: 1px solid rgba(0, 0, 0, 0.12);
    background: transparent;
    border-radius: 8px;
    padding: 6px 10px;
    cursor: pointer;
  }
  .secret-ref {
    margin-top: 6px;
  }
  .hint {
    margin-top: 6px;
    font-size: 0.85rem;
    opacity: 0.8;
  }

  /* Storage-endpoint wizard alignment (minimal, keeps your existing classes) */
  .se-password {
    display: flex;
    gap: 8px;
    align-items: center;
  }
  .se-eye {
    border: 1px solid rgba(0, 0, 0, 0.12);
    background: transparent;
    border-radius: 10px;
    padding: 6px 10px;
    cursor: pointer;
  }
</style>
