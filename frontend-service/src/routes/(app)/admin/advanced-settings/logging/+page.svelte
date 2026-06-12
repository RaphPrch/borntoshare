<script lang="ts">
  import ConfigCard from '$lib/components/advanced-settings/v3/ConfigCard.svelte';
  import DangerZone from '$lib/components/advanced-settings/v3/DangerZone.svelte';
  import ConfirmActionModal from '$lib/components/common/ConfirmActionModal.svelte';
  import SettingRow from '$lib/components/advanced-settings/v3/SettingRow.svelte';

  import { toasts } from '$lib/stores/toast';
  import { notifyError, toAppError } from '$lib/core/errors';
  import { logAppError } from '$lib/core/logging';
  import type { LogLevel } from '$lib/api/admin-advanced-settings';
  import { saveLoggingConfig, purgeLogs } from '$lib/api/admin-advanced-settings';

  export let data: any;
  const settings = data.settings;

  const initialLogging = {
    level: String(settings.logging.level ?? 'INFO'),
    retentionEnabled: Boolean(settings.logging.retentionEnabled ?? true),
    retentionDays: Number(settings.logging.retentionDays ?? 180)
  };

  let form = { ...initialLogging };
  let saving = false;
  let purging = false;
  let purgeConfirmOpen = false;
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

  const levels: LogLevel[] = ['DEBUG', 'INFO', 'WARN', 'ERROR'];
  const clamp = (n: number, min: number, max: number) => Math.min(max, Math.max(min, n));
  const normalize = (input: typeof form) => ({
    level: (levels.includes(input.level as LogLevel) ? input.level : 'INFO') as LogLevel,
    retentionEnabled: Boolean(input.retentionEnabled),
    retentionDays: clamp(Number(input.retentionDays ?? 180), 1, 3650)
  });

  let initialSnapshot = JSON.stringify(normalize(initialLogging));

  $: retentionError =
    form.retentionEnabled && !(Number(form.retentionDays) >= 1 && Number(form.retentionDays) <= 3650)
      ? 'Retention must be between 1 and 3650 days.'
      : null;
  $: levelError = levels.includes(String(form.level)) ? null : 'Invalid log level.';
  $: hasErrors = Boolean(retentionError || levelError);
  $: isDirty = JSON.stringify(normalize(form)) !== initialSnapshot;
  $: canSave = !saving && isDirty && !hasErrors;

  async function save() {
    if (!canSave) return;
    saving = true;
    errorMsg = null;
    try {
      const payload = normalize(form);
      await saveLoggingConfig(fetch, {
        level: payload.level,
        retentionEnabled: payload.retentionEnabled,
        retentionDays: payload.retentionDays
      });
      settings.logging = { ...settings.logging, ...payload };
      form = { ...payload };
      initialSnapshot = JSON.stringify(normalize(payload));
      toasts.success('Logging settings saved.');
    } catch (e: unknown) {
      errorMsg = toUiErrorMessage(e, 'Failed to save logging settings.', 'advanced_settings.logging.save');
    } finally {
      saving = false;
    }
  }

  function purge() {
    if (purging) return;
    purgeConfirmOpen = true;
  }

  async function confirmPurge() {
    if (purging) return;
    purgeConfirmOpen = false;
    purging = true;
    try {
      await purgeLogs(fetch);
      toasts.success('Purge requested.');
    } catch (e: unknown) {
      toUiErrorMessage(e, 'Backend not connected: simulated action (dev).', 'advanced_settings.logging.purge');
    } finally {
      purging = false;
    }
  }
</script>

<ConfigCard title="Logging" subtitle="Persisted configuration" icon="bi-journal-text">
  <div class="adv-form-grid">
    <SettingRow label="Log level">
      <select class="form-select" bind:value={form.level}>
        <option value="DEBUG">DEBUG</option>
        <option value="INFO">INFO</option>
        <option value="WARN">WARN</option>
        <option value="ERROR">ERROR</option>
      </select>
      {#if levelError}
        <div class="adv-inline-error">{levelError}</div>
      {/if}
    </SettingRow>

    <SettingRow label="Retention (days)">
      <input
        class="form-control"
        type="number"
        min="1"
        step="1"
        bind:value={form.retentionDays}
        disabled={!form.retentionEnabled}
      />
      {#if retentionError}
        <div class="adv-inline-error">{retentionError}</div>
      {/if}
    </SettingRow>

    <SettingRow label="Retention enabled">
      <div class="form-check form-switch">
        <input
          id="retention-enabled"
          class="form-check-input"
          type="checkbox"
          bind:checked={form.retentionEnabled}
        />
        <label class="form-check-label" for="retention-enabled">Enable log retention</label>
      </div>
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

<DangerZone title="Danger zone" subtitle="Cleanup / purge">
  <div class="adv-btn-row">
    <button class="btn btn-danger" type="button" on:click={purge} disabled={purging}>
      <i class="bi bi-trash"></i> Purge old logs
    </button>
  </div>
</DangerZone>

<ConfirmActionModal
  open={purgeConfirmOpen}
  onClose={() => (purgeConfirmOpen = false)}
  onConfirm={confirmPurge}
  severity="danger"
  title="Purge logs"
  subtitle="This action is irreversible."
  impactTitle="Impact"
  impactItems={[
    'Historical logs will be removed according to backend retention purge rules.',
    'This cannot be undone.'
  ]}
  cancelLabel="Cancel"
  confirmLabel="Purge"
  confirmBusyLabel="Purging…"
  busy={purging}
/>
