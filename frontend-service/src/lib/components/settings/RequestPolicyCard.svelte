<script lang="ts">
  import { guardUnsaved } from '$lib/utils/unsaved';
  import { t } from '$lib/i18n';
  import ConfigCard from '$lib/components/settings/ConfigCard.svelte';
  import SettingRow from '$lib/components/settings/SettingRow.svelte';
  import { toast } from '$lib/stores/toast';
  import { reportUiError } from '$lib/errors';
  import { saveAdvancedSections } from '$lib/api/admin-advanced-settings';

  
  interface Props {
    /** Advanced settings › Governance: the durations offered to a new request, the longest access, the reason. */
    requests?: { durations?: number[]; allowPermanent?: boolean; maxDays?: number; minReasonLength?: number; decisionDays?: number; escalationDays?: number };
  }

  let { requests = {} }: Props = $props();

  // svelte-ignore state_referenced_locally (an initial value, read once as before)
  let durations = $state([...(requests.durations ?? [7, 30, 90])]);
  // Not shown any more (Advanced settings › Governance): the value saved stays as it is
  // svelte-ignore state_referenced_locally (an initial value, read once as before)
  const allowPermanent = requests.allowPermanent ?? true;
  // svelte-ignore state_referenced_locally (an initial value, read once as before)
  let maxDays = $state(requests.maxDays ?? 365);
  // svelte-ignore state_referenced_locally (an initial value, read once as before)
  let minReasonLength = $state(requests.minReasonLength ?? 10);
  // Decision deadline: the guardians are reminded daily past it; the administrators are told after the escalation (0: never)
  // svelte-ignore state_referenced_locally (an initial value, read once as before)
  let decisionDays = $state(requests.decisionDays ?? 3);
  // svelte-ignore state_referenced_locally (an initial value, read once as before)
  let escalationDays = $state(requests.escalationDays ?? 7);
  let newDuration = $state('');
  let saving = $state(false);
  const snap = () => JSON.stringify([durations, allowPermanent, Number(maxDays), Number(minReasonLength), Number(decisionDays), Number(escalationDays)]);
  let savedSnap = snap();
  guardUnsaved(() => snap() !== savedSnap);

  function addDuration() {
    const days = Number(newDuration);
    if (Number.isInteger(days) && days > 0 && days <= 3650 && !durations.includes(days)) durations = [...durations, days].sort((a, b) => a - b);
    newDuration = '';
  }
  let error = $derived(!durations.length && !allowPermanent
    ? t('Offer at least one duration.')
    : durations.some((days) => days > maxDays)
      ? t('A duration offered goes beyond the longest access.')
      : !(Number(decisionDays) >= 1 && Number(decisionDays) <= 60)
        ? t('The decision deadline goes from 1 to 60 days.')
        : Number(escalationDays) !== 0 && Number(escalationDays) < Number(decisionDays)
          ? t('The escalation comes after the decision deadline (0: never).')
          : null);

  async function save() {
    saving = true;
    try {
      await saveAdvancedSections(fetch, { requests: { durations, allowPermanent, maxDays: Number(maxDays), minReasonLength: Number(minReasonLength),
        decisionDays: Number(decisionDays), escalationDays: Number(escalationDays) } });
      savedSnap = snap();
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
          <span class="rp__chip">{t('{count} days', { count: days })}<button type="button" aria-label={t('Remove')} onclick={() => (durations = durations.filter((d) => d !== days))}>×</button></span>
        {/each}
        <input class="b2s-input rp__add" type="number" min="1" max="3650" bind:value={newDuration} placeholder={t('days')} onkeydown={(e) => e.key === 'Enter' && addDuration()} aria-label={t('Add a duration')} />
        <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" onclick={addDuration}>{t('Add')}</button>
      </div>
      <small class="adv-hint">{t('The requester can also pick a date, within the longest access.')}</small>
    </SettingRow>
    <SettingRow label={t('Longest access (days)')}>
      <input class="b2s-input" type="number" min="1" max="3650" bind:value={maxDays} />
    </SettingRow>
    <SettingRow label={t('Shortest reason (characters)')}>
      <input class="b2s-input" type="number" min="1" max="500" bind:value={minReasonLength} />
    </SettingRow>
    <SettingRow label={t('Decision deadline (days)')}>
      <input class="b2s-input" type="number" min="1" max="60" bind:value={decisionDays} />
      <small class="adv-hint">{t('Past it, the request is overdue and its guardians are reminded once a day.')}</small>
    </SettingRow>
    <SettingRow label={t('Tell the administrators after (days)')}>
      <input class="b2s-input" type="number" min="0" max="365" bind:value={escalationDays} />
      <small class="adv-hint">{t('A request still without decision is told to the administrators once a day; 0: never.')}</small>
    </SettingRow>
  </div>
  {#if error}<small class="rp__error">{error}</small>{/if}
  <div class="adv-actions">
    <button class="b2s-btn b2s-btn-primary" type="button" onclick={save} disabled={saving || Boolean(error)}><i class="bi bi-check2" aria-hidden="true"></i>{saving ? t('Saving…') : t('Save changes')}</button>
  </div>
</ConfigCard>

<style>
  .rp__chips { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
  .rp__chip { display: inline-flex; align-items: center; gap: 4px; padding: 3px 4px 3px 10px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-pill); font-size: var(--b2s-fs-sm); }
  .rp__chip button { border: 0; background: none; color: var(--b2s-color-text-muted); cursor: pointer; }
  .rp__add { width: 90px; }
  .rp__error { color: var(--b2s-color-danger-strong); }
</style>
