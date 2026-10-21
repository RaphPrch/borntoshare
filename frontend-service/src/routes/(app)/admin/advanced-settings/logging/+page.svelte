<script lang="ts">
  import FieldError from '$lib/components/ui/FieldError.svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import { t } from '$lib/i18n';
  import { clamp } from '$lib/utils/values';
  import ConfigCard from '$lib/components/settings/ConfigCard.svelte';
  import DangerZone from '$lib/components/settings/DangerZone.svelte';
  import ConfirmActionModal from '$lib/components/ui/ConfirmActionModal.svelte';
  import SettingRow from '$lib/components/settings/SettingRow.svelte';

  import { toast } from '$lib/stores/toast';
  import { reportUiError } from '$lib/errors';
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

  const levels: LogLevel[] = ['DEBUG', 'INFO', 'WARN', 'ERROR'];
  const normalize = (input: typeof form) => ({
    level: (levels.includes(input.level as LogLevel) ? input.level : 'INFO') as LogLevel,
    retentionEnabled: Boolean(input.retentionEnabled),
    retentionDays: clamp(Number(input.retentionDays ?? 180), 1, 3650)
  });

  let initialSnapshot = JSON.stringify(normalize(initialLogging));

  $: retentionError =
    form.retentionEnabled && !(Number(form.retentionDays) >= 1 && Number(form.retentionDays) <= 3650)
      ? t('Retention must be between 1 and 3650 days.')
      : null;
  $: levelError = levels.includes(form.level as LogLevel) ? null : t('Invalid log level.');
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
      toast.success(t('Logging settings saved.'));
    } catch (e: unknown) {
      errorMsg = reportUiError(e, 'Failed to save logging settings.', 'advanced_settings.logging.save');
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
      toast.success(t('Purge requested.'));
    } catch (e: unknown) {
      reportUiError(e, 'Backend not connected: simulated action (dev).', 'advanced_settings.logging.purge');
    } finally {
      purging = false;
    }
  }
</script>

<ConfigCard title={t('Logging')} subtitle={t('Persisted configuration')} icon="bi-journal-text">
  <div class="adv-form-grid">
    <SettingRow label={t('Log level')}>
      <select class="form-select" bind:value={form.level}>
        <option value="DEBUG">DEBUG</option>
        <option value="INFO">INFO</option>
        <option value="WARN">WARN</option>
        <option value="ERROR">ERROR</option>
      </select>
      {#if levelError}
        <FieldError>{levelError}</FieldError>
      {/if}
    </SettingRow>

    <SettingRow label={t('Retention (days)')}>
      <input
        class="form-control"
        type="number"
        min="1"
        step="1"
        bind:value={form.retentionDays}
        disabled={!form.retentionEnabled}
      />
      {#if retentionError}
        <FieldError>{retentionError}</FieldError>
      {/if}
    </SettingRow>

    <SettingRow label={t('Retention enabled')}>
      <div class="form-check form-switch">
        <input
          id="retention-enabled"
          class="form-check-input"
          type="checkbox"
          bind:checked={form.retentionEnabled}
        />
        <label class="form-check-label" for="retention-enabled">{t('Enable log retention')}</label>
      </div>
    </SettingRow>
  </div>

  {#if errorMsg}
    <InlineAlert tone="error">{errorMsg}</InlineAlert>
  {/if}

  <div class="adv-actions">
    <button class="b2s-btn b2s-btn-primary" type="button" on:click={save} disabled={!canSave}>
      {saving ? t('Saving…') : t('Save changes')}
    </button>
  </div>
</ConfigCard>

<DangerZone title={t('Danger zone')} subtitle={t('Cleanup / purge')}>
  <div class="adv-btn-row">
    <button class="b2s-btn b2s-btn-danger" type="button" on:click={purge} disabled={purging}>
      <i class="bi bi-trash"></i> {t('Purge old logs')}
    </button>
  </div>
</DangerZone>

<ConfirmActionModal
  open={purgeConfirmOpen}
  onClose={() => (purgeConfirmOpen = false)}
  onConfirm={confirmPurge}
  severity="danger"
  title={t('Purge logs')}
  subtitle={t('This action is irreversible.')}
  impactTitle={t('Impact')}
  impactItems={[
    'Historical logs will be removed according to backend retention purge rules.',
    'This cannot be undone.'
  ]}
  cancelLabel={t('Cancel')}
  confirmLabel={t('Purge')}
  confirmBusyLabel={t('Purging…')}
  busy={purging}
/>
