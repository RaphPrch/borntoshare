<script lang="ts">
  import FieldError from '$lib/components/ui/FieldError.svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import { t } from '$lib/i18n';
  import ConfigCard from '$lib/components/settings/ConfigCard.svelte';
  import SettingRow from '$lib/components/settings/SettingRow.svelte';

  import { toast } from '$lib/stores/toast';
  import { reportUiError } from '$lib/errors';
  import { saveGovernanceConfig } from '$lib/api/admin-advanced-settings';

  export let data: any;

  let minGuardians = Number(data.settings.governance.minGuardians ?? 2);
  let saved = minGuardians;
  let saving = false;
  let errorMsg: string | null = null;

  $: rangeError = Number.isInteger(Number(minGuardians)) && minGuardians >= 1 && minGuardians <= 10
    ? null
    : t('Enter a number between 1 and 10.');
  $: canSave = !saving && !rangeError && Number(minGuardians) !== saved;

  async function save() {
    if (!canSave) return;
    saving = true;
    errorMsg = null;
    try {
      await saveGovernanceConfig(fetch, Number(minGuardians));
      saved = Number(minGuardians);
      toast.success(t('Governance settings saved.'));
    } catch (e: unknown) {
      errorMsg = reportUiError(e, 'Failed to save governance settings.', 'advanced_settings.governance.save');
    } finally {
      saving = false;
    }
  }
</script>

<ConfigCard title={t('Governance')} subtitle={t('Rules every governed folder must follow.')}>
  <div class="adv-form-grid">
    <SettingRow label={t('Minimum guardians per folder')}>
      <input class="form-control" type="number" min="1" max="10" step="1" bind:value={minGuardians} />
      {#if rangeError}
        <FieldError>{rangeError}</FieldError>
      {/if}
      <small class="adv-hint">{t('Saving the guardians of a folder is refused below this number. Folders already below it get an alert.')}</small>
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
