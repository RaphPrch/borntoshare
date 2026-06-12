<script lang="ts">
  import ConfigCard from '$lib/components/advanced-settings/v3/ConfigCard.svelte';
  import SettingRow from '$lib/components/advanced-settings/v3/SettingRow.svelte';

  import { toasts } from '$lib/stores/toast';
  import { notifyError, toAppError } from '$lib/core/errors';
  import { logAppError } from '$lib/core/logging';
  import { saveSecurityConfig } from '$lib/api/admin-advanced-settings';

  export let data: any;
  const settings = data.settings;
  const initialSecurity = {
    enforceStrongPasswords: Boolean(settings.security.enforceStrongPasswords),
    passwordMinLength: Number(settings.security.passwordMinLength ?? 10),
    passwordHistory: Number(settings.security.passwordHistory ?? 5),
    passwordExpiryDays: Number(settings.security.passwordExpiryDays ?? 90)
  };

  let form = { ...initialSecurity };
  let saving = false;
  let errorMsg: string | null = null;

  const GENERIC_ERROR_MESSAGES = new Set(['Unexpected error', 'Backend error', 'Network error', 'Request timeout']);

  const toUiErrorMessage = (error: unknown, fallback: string, action: string): string => {
    const normalized = toAppError(error, { source: 'ui' });
    const appError = GENERIC_ERROR_MESSAGES.has(normalized.message)
      ? { ...normalized, message: fallback }
      : normalized;
    logAppError(appError, { action });
    notifyError(appError);
    return appError.message;
  };

  const clamp = (n: number, min: number, max: number) => Math.min(max, Math.max(min, n));
  const normalize = (input: typeof form) => ({
    enforceStrongPasswords: Boolean(input.enforceStrongPasswords),
    passwordMinLength: clamp(Number(input.passwordMinLength ?? 10), 8, 64),
    passwordHistory: clamp(Number(input.passwordHistory ?? 5), 0, 24),
    passwordExpiryDays: clamp(Number(input.passwordExpiryDays ?? 90), 0, 365)
  });

  let initialSnapshot = JSON.stringify(normalize(initialSecurity));

  $: minLengthError = Number(form.passwordMinLength) >= 8 && Number(form.passwordMinLength) <= 64
    ? null
    : 'Minimum length must be between 8 and 64.';
  $: historyError = Number(form.passwordHistory) >= 0 && Number(form.passwordHistory) <= 24
    ? null
    : 'History must be between 0 and 24.';
  $: expiryError = Number(form.passwordExpiryDays) >= 0 && Number(form.passwordExpiryDays) <= 365
    ? null
    : 'Expiration must be between 0 and 365 days.';
  $: hasErrors = Boolean(minLengthError || historyError || expiryError);
  $: isDirty = JSON.stringify(normalize(form)) !== initialSnapshot;
  $: canSave = !saving && isDirty && !hasErrors;

  async function save() {
    if (!canSave) return;
    saving = true;
    errorMsg = null;
    try {
      const payload = normalize(form);
      await saveSecurityConfig(fetch, payload);
      settings.security = { ...settings.security, ...payload };
      form = { ...payload };
      initialSnapshot = JSON.stringify(normalize(payload));
      toasts.success('Security settings saved.');
    } catch (e: unknown) {
      errorMsg = toUiErrorMessage(e, 'Unable to save.', 'advanced_settings.security.save');
    } finally {
      saving = false;
    }
  }
</script>

<ConfigCard title="Password policy" subtitle="Comptes locaux uniquement (dev)" icon="bi-key">
  <div class="adv-form-grid">
    <SettingRow
      label="Enforce strong passwords"
      help="Disabled by default to avoid blocking your HTTP-only mode (dev)."
    >
      <label class="checkbox">
        <input type="checkbox" bind:checked={form.enforceStrongPasswords} />
        <span>Enabled</span>
      </label>
    </SettingRow>

    <SettingRow label="Minimum length">
      <input class="form-control" type="number" min="8" max="64" bind:value={form.passwordMinLength} />
      {#if minLengthError}
        <div class="adv-inline-error">{minLengthError}</div>
      {/if}
    </SettingRow>

    <SettingRow label="Password history">
      <input class="form-control" type="number" min="0" max="24" bind:value={form.passwordHistory} />
      {#if historyError}
        <div class="adv-inline-error">{historyError}</div>
      {/if}
    </SettingRow>

    <SettingRow label="Expiry (days)">
      <input class="form-control" type="number" min="0" max="365" bind:value={form.passwordExpiryDays} />
      {#if expiryError}
        <div class="adv-inline-error">{expiryError}</div>
      {/if}
    </SettingRow>
  </div>

  {#if errorMsg}
    <div class="adv-inline-error adv-inline-error--block">{errorMsg}</div>
  {/if}

  <div class="adv-actions">
    <button class="btn btn-primary" type="button" on:click={save} disabled={!canSave}>
      {saving ? 'Saving…' : 'Save changes'}
    </button>
  </div>
</ConfigCard>
