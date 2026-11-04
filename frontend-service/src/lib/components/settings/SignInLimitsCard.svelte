<script lang="ts">
  import { t } from '$lib/i18n';
  import ConfigCard from '$lib/components/settings/ConfigCard.svelte';
  import SettingRow from '$lib/components/settings/SettingRow.svelte';
  import { toast } from '$lib/stores/toast';
  import { reportUiError } from '$lib/errors';
  import { saveAdvancedSections } from '$lib/api/admin-advanced-settings';

  /** Advanced settings › User sessions: failed sign-ins before a pause (applied by auth-service within a minute). */
  export let signIn: { maxFailuresPerAccount?: number; maxFailuresPerAddress?: number; windowMinutes?: number } = {};

  let perAccount = signIn.maxFailuresPerAccount ?? 5;
  let perAddress = signIn.maxFailuresPerAddress ?? 50;
  let windowMinutes = signIn.windowMinutes ?? 15;
  let saving = false;
  async function save() {
    saving = true;
    try {
      await saveAdvancedSections(fetch, { signIn: { maxFailuresPerAccount: Number(perAccount), maxFailuresPerAddress: Number(perAddress), windowMinutes: Number(windowMinutes) } });
      toast.success(t('Sign-in limits saved.'));
    } catch (e) {
      reportUiError(e, t('Unable to save the sign-in limits.'), 'advanced_settings.sign_in.save');
    } finally {
      saving = false;
    }
  }
</script>

<ConfigCard title={t('Failed sign-ins')} subtitle={t('Beyond these failures, the next attempts wait until the window has passed.')}>
  <div class="adv-form-grid">
    <SettingRow label={t('Failures per account')}><input class="b2s-input" type="number" min="3" max="50" bind:value={perAccount} /></SettingRow>
    <SettingRow label={t('Failures per address')}><input class="b2s-input" type="number" min="10" max="1000" bind:value={perAddress} /></SettingRow>
    <SettingRow label={t('Window (minutes)')}><input class="b2s-input" type="number" min="1" max="1440" bind:value={windowMinutes} /></SettingRow>
  </div>
  <div class="adv-actions">
    <button class="b2s-btn b2s-btn-primary" type="button" on:click={save} disabled={saving}><i class="bi bi-check2" aria-hidden="true"></i>{saving ? t('Saving…') : t('Save changes')}</button>
  </div>
</ConfigCard>
