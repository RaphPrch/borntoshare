<script lang="ts">
  import { t } from '$lib/i18n';
  import ConfigCard from '$lib/components/settings/ConfigCard.svelte';
  import SettingRow from '$lib/components/settings/SettingRow.svelte';
  import { toast } from '$lib/stores/toast';
  import { reportUiError } from '$lib/errors';
  import { saveAdvancedSections } from '$lib/api/admin-advanced-settings';

  /** Advanced settings › Governance: the durations offered to a new request, the permanent access, the reason. */
  export let requests: { durations?: number[]; allowPermanent?: boolean; maxDays?: number; minReasonLength?: number } = {};

  let durations = [...(requests.durations ?? [7, 30, 90])];
  let allowPermanent = requests.allowPermanent ?? true;
  let maxDays = requests.maxDays ?? 365;
  let minReasonLength = requests.minReasonLength ?? 10;
  let newDuration = '';
  let saving = false;

  function addDuration() {
    const days = Number(newDuration);
    if (Number.isInteger(days) && days > 0 && days <= 3650 && !durations.includes(days)) durations = [...durations, days].sort((a, b) => a - b);
    newDuration = '';
  }
  $: error = !durations.length && !allowPermanent
    ? t('Offer at least one duration, or allow the permanent access.')
    : durations.some((days) => days > maxDays)
      ? t('A duration offered goes beyond the longest access.')
      : null;

  async function save() {
    saving = true;
    try {
      await saveAdvancedSections(fetch, { requests: { durations, allowPermanent, maxDays: Number(maxDays), minReasonLength: Number(minReasonLength) } });
      toast.success(t('Request policy saved.'));
    } catch (e) {
      reportUiError(e, t('Unable to save the request policy.'), 'advanced_settings.requests.save');
    } finally {
      saving = false;
    }
  }
</script>

<ConfigCard title={t('Access requests')} subtitle={t('What a new request offers, and what core-service refuses.')}>
  <div class="adv-form-grid">
    <SettingRow label={t('Durations offered')}>
      <div class="rp__chips">
        {#each durations as days (days)}
          <span class="rp__chip">{t('{count} days', { count: days })}<button type="button" aria-label={t('Remove')} on:click={() => (durations = durations.filter((d) => d !== days))}>×</button></span>
        {/each}
        <input class="b2s-input rp__add" type="number" min="1" max="3650" bind:value={newDuration} placeholder={t('days')} on:keydown={(e) => e.key === 'Enter' && addDuration()} aria-label={t('Add a duration')} />
        <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" on:click={addDuration}>{t('Add')}</button>
      </div>
      <small class="adv-hint">{t('The requester can also pick a date, within the longest access.')}</small>
    </SettingRow>
    <SettingRow label={t('Longest access (days)')}>
      <input class="b2s-input" type="number" min="1" max="3650" bind:value={maxDays} />
    </SettingRow>
    <SettingRow label={t('Permanent access')}>
      <div class="form-check form-switch">
        <input class="form-check-input" type="checkbox" role="switch" id="rp-permanent" bind:checked={allowPermanent} />
        <label class="form-check-label" for="rp-permanent">{allowPermanent ? t('Allowed') : t('Refused: every access has an end date')}</label>
      </div>
    </SettingRow>
    <SettingRow label={t('Shortest reason (characters)')}>
      <input class="b2s-input" type="number" min="1" max="500" bind:value={minReasonLength} />
    </SettingRow>
  </div>
  {#if error}<small class="rp__error">{error}</small>{/if}
  <div class="adv-actions">
    <button class="b2s-btn b2s-btn-primary" type="button" on:click={save} disabled={saving || Boolean(error)}><i class="bi bi-check2" aria-hidden="true"></i>{saving ? t('Saving…') : t('Save changes')}</button>
  </div>
</ConfigCard>

<style>
  .rp__chips { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
  .rp__chip { display: inline-flex; align-items: center; gap: 4px; padding: 3px 4px 3px 10px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-pill); font-size: var(--b2s-fs-sm); }
  .rp__chip button { border: 0; background: none; color: var(--b2s-color-text-muted); cursor: pointer; }
  .rp__add { width: 90px; }
  .rp__error { color: var(--b2s-color-danger-strong); }
</style>
