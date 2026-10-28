<script lang="ts">
  import { t } from '$lib/i18n';
  import FieldError from '$lib/components/ui/FieldError.svelte';
  import type { ServiceAccountDraft } from '$lib/utils/service-accounts';

  export let idPrefix: string;
  export let icon: string;
  export let title: string;
  export let description: string;
  export let draft: ServiceAccountDraft;
  export let showErrors = false;
  export let placeholder = 'svc-account@example.test';
  /** Probe the directory with this account; null hides the button */
  export let onTest: (() => Promise<boolean>) | null = null;

  let testState: 'idle' | 'running' | 'ok' | 'failed' = 'idle';
  // The result is for the account tested: a new DN or password needs a new test
  $: draftKey = `${draft.bind_dn}|${draft.password}`;
  let testedKey = '';
  $: if (testState !== 'idle' && testState !== 'running' && draftKey !== testedKey) testState = 'idle';
  $: canTest = !!onTest && !!draft.bind_dn.trim() && (!!draft.password.trim() || draft.has_password);

  async function runTest() {
    if (!onTest || testState === 'running') return;
    testState = 'running';
    testedKey = draftKey;
    try {
      testState = (await onTest()) ? 'ok' : 'failed';
    } catch {
      testState = 'failed';
    }
  }

  let showPassword = false;
</script>

<div class="sa" class:sa--on={draft.dedicated}>
  <div class="sa-head">
    <span class="sa-icon"><i class={`bi ${icon}`} aria-hidden="true"></i></span>
    <span class="sa-copy">
      <strong>{title}</strong>
      <small>
        {draft.dedicated ? description : t('Uses the main service account.')}
      </small>
    </span>
    <label class="sa-toggle" for={`${idPrefix}-dedicated`}>
      <span>{t('Dedicated account')}</span>
      <input id={`${idPrefix}-dedicated`} class="cap-switch" type="checkbox" bind:checked={draft.dedicated} />
    </label>
  </div>

  {#if draft.dedicated}
    <div class="sa-fields">
      <div class="sa-field">
        <label for={`${idPrefix}-bind-dn`}>{t('Bind DN')}</label>
        <input id={`${idPrefix}-bind-dn`} bind:value={draft.bind_dn} {placeholder} autocomplete="off" />
        {#if showErrors && !draft.bind_dn.trim()}
          <FieldError>{t('Required')}</FieldError>
        {/if}
      </div>
      <div class="sa-field">
        <label for={`${idPrefix}-password`}>{t('Bind password')}</label>
        <div class="b2s-input-with-action">
          <input
            id={`${idPrefix}-password`}
            type={showPassword ? 'text' : 'password'}
            bind:value={draft.password}
            autocomplete="new-password"
            placeholder={draft.has_password ? t('Unchanged') : ''}
          />
          <button
            class="b2s-input-action"
            type="button"
            aria-label={showPassword ? t('Hide password') : t('Show password')}
            on:click={() => (showPassword = !showPassword)}
          >
            <i class={`bi ${showPassword ? 'bi-eye-slash' : 'bi-eye'}`} aria-hidden="true"></i>
          </button>
        </div>
        {#if showErrors && !draft.password.trim() && !draft.has_password}
          <FieldError>{t('Required')}</FieldError>
        {:else if draft.has_password && !draft.password}
          <span class="sa-hint">{t('A password is stored. Leave empty to keep it.')}</span>
        {/if}
      </div>
      {#if onTest}
        <div class="sa-test">
          <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" disabled={!canTest || testState === 'running'} on:click={runTest}>
            <i class={`bi ${testState === 'running' ? 'bi-hourglass-split' : 'bi-activity'}`} aria-hidden="true"></i>
            {testState === 'running' ? t('Testing…') : t('Test this account')}
          </button>
          {#if testState === 'ok'}
            <span class="sa-result is-ok"><i class="bi bi-check-circle-fill" aria-hidden="true"></i> {t('Connection validated.')}</span>
          {:else if testState === 'failed'}
            <span class="sa-result is-err"><i class="bi bi-x-circle-fill" aria-hidden="true"></i> {t('Connection failed')}</span>
          {/if}
        </div>
      {/if}
    </div>
  {/if}
</div>

<style>
  .sa {
    border: 1px solid #d9e2ef;
    border-radius: var(--b2s-radius-sm);
    background: #ffffff;
    padding: 10px 12px;
  }

  .sa--on {
    border-color: #b9cdf0;
    background: #f8fbff;
  }

  .sa-head {
    display: grid;
    grid-template-columns: auto 1fr auto;
    gap: 10px;
    align-items: center;
  }

  .sa-icon {
    width: 28px;
    height: 28px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: var(--b2s-radius-sm);
    background: #eff6ff;
    color: #0b63f4;
  }

  .sa-copy {
    min-width: 0;
  }

  .sa-copy strong,
  .sa-copy small {
    display: block;
  }

  .sa-copy strong {
    color: #071638;
    font-size: var(--b2s-fs-xs);
    font-weight: 700;
  }

  .sa-copy small {
    margin-top: 2px;
    color: #596985;
    font-size: var(--b2s-fs-xs);
  }

  .sa-toggle {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    font-size: var(--b2s-fs-xs);
    color: #334155;
    cursor: pointer;
    white-space: nowrap;
  }

  .sa-fields {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
    margin-top: 10px;
  }

  .sa-field {
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-width: 0;
  }

  .sa-field label {
    font-size: var(--b2s-fs-xs);
    font-weight: 600;
    color: #334155;
  }

  /* Same field as the rest of the identity source forms */
  .sa-field input {
    width: 100%;
    height: 38px;
    padding: 0 12px;
    border: 1px solid #d9e2ef;
    border-radius: var(--b2s-radius-sm);
    background: #ffffff;
    color: #071638;
    font-size: var(--b2s-fs-sm);
    outline: 0;
  }

  .sa-field input:focus {
    border-color: #8db5ff;
    box-shadow: 0 0 0 3px rgba(11, 99, 244, 0.12);
  }

  .sa-field :global(.b2s-input-with-action input) {
    padding-right: 44px;
  }

  .sa-test {
    grid-column: 1 / -1;
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .sa-result {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: var(--b2s-fs-xs);
  }

  .sa-result.is-ok {
    color: #15803d;
  }

  .sa-result.is-err {
    color: #b91c1c;
  }

  .sa-hint {
    font-size: var(--b2s-fs-xs);
    color: #64748b;
  }

  .cap-switch {
    appearance: none;
    flex: none;
    width: 34px;
    height: 19px;
    border-radius: var(--b2s-radius-pill);
    background: #cbd5e1;
    position: relative;
    cursor: pointer;
    transition: background 0.16s ease;
  }

  .cap-switch::after {
    content: "";
    position: absolute;
    top: 3px;
    left: 3px;
    width: 13px;
    height: 13px;
    border-radius: 50%;
    background: #ffffff;
    transition: transform 0.16s ease;
  }

  .cap-switch:checked {
    background: var(--b2s-topbar-bg, #0b1530);
  }

  .cap-switch:checked::after {
    transform: translateX(15px);
  }

  @media (max-width: 640px) {
    .sa-head {
      grid-template-columns: auto 1fr;
    }

    .sa-toggle {
      grid-column: 1 / -1;
    }

    .sa-fields {
      grid-template-columns: 1fr;
    }
  }
</style>
