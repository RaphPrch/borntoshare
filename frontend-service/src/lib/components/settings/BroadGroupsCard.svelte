<script lang="ts">
  import { t } from '$lib/i18n';
  import ConfigCard from '$lib/components/settings/ConfigCard.svelte';
  import { toast } from '$lib/stores/toast';
  import { reportUiError } from '$lib/errors';
  import { saveAdvancedSections } from '$lib/api/admin-advanced-settings';

  /** Advanced settings › Governance: groups that open a folder to everyone, besides the built-in ones. */
  export let groups: string[] = [];

  let list = [...groups];
  let draft = '';
  let saving = false;
  function add() {
    const name = draft.trim();
    if (name && !list.some((g) => g.toLowerCase() === name.toLowerCase())) list = [...list, name];
    draft = '';
  }
  async function save() {
    saving = true;
    try {
      await saveAdvancedSections(fetch, { exposure: { broadGroups: list } });
      toast.success(t('Broad groups saved.'));
    } catch (e) {
      reportUiError(e, t('Unable to save the broad groups.'), 'advanced_settings.exposure.save');
    } finally {
      saving = false;
    }
  }
</script>

<ConfigCard title={t('Groups open to everyone')} subtitle={t('Everyone, Users and Domain users already count. Add the groups of your company that hold every employee.')}>
  <div class="bg__list">
    {#each list as group (group)}
      <span class="bg__chip">{group}<button type="button" aria-label={t('Remove')} on:click={() => (list = list.filter((g) => g !== group))}>×</button></span>
    {:else}
      <small class="adv-hint">{t('No group added.')}</small>
    {/each}
  </div>
  <div class="bg__add">
    <input class="b2s-input" bind:value={draft} placeholder={t('e.g. CORP\\GG_All_Staff')} on:keydown={(e) => e.key === 'Enter' && add()} aria-label={t('Group name')} />
    <button type="button" class="b2s-btn b2s-btn-secondary" on:click={add}>{t('Add')}</button>
  </div>
  <small class="adv-hint">{t('A folder these groups reach is « open to everyone » on the exposure map and in the alerts.')}</small>
  <div class="adv-actions">
    <button class="b2s-btn b2s-btn-primary" type="button" on:click={save} disabled={saving}><i class="bi bi-check2" aria-hidden="true"></i>{saving ? t('Saving…') : t('Save changes')}</button>
  </div>
</ConfigCard>

<style>
  .bg__list { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }
  .bg__chip { display: inline-flex; align-items: center; gap: 4px; padding: 3px 4px 3px 10px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-pill); font-family: var(--b2s-font-mono); font-size: var(--b2s-fs-xs); }
  .bg__chip button { border: 0; background: none; color: var(--b2s-color-text-muted); cursor: pointer; }
  .bg__add { display: flex; gap: 8px; max-width: 520px; }
</style>
