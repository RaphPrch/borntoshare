<script lang="ts">
  import { apiGetData, apiPostData } from '$lib/api/client';
  import AppModal from '$lib/components/ui/AppModal.svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import { reportUiError } from '$lib/errors';
  import { t } from '$lib/i18n';

  /**
   * Deleting or disabling a person: the folders they would leave without any active guardian are listed, and
   * someone takes them over before the change (the server refuses it otherwise).
   */
  export let open = false;
  export let identity: Record<string, any> | null = null;
  export let mode: 'delete' | 'disable' = 'delete';
  export let candidates: Array<Record<string, any>> = [];
  export let onClose: () => void = () => {};
  export let onConfirm: () => Promise<void> = async () => {};

  type Folder = { id: number; name: string; path: string };
  let orphaned: Folder[] | null = null;
  let heir = 0;
  let busy = false;
  let loadedFor = '';
  $: key = open && identity ? `${mode}:${identity.id}` : '';
  $: if (key && key !== loadedFor) load();
  async function load() {
    loadedFor = key;
    orphaned = null;
    heir = 0;
    try {
      orphaned = (await apiGetData<{ orphaned: Folder[] }>(fetch, `/identity/${identity!.id}/handover`))?.orphaned ?? [];
    } catch {
      orphaned = [];
    }
  }
  $: people = candidates.filter((item) => String(item.type ?? 'user') !== 'group' && item.status !== 'inactive' && item.is_active !== false && Number(item.id) !== Number(identity?.id));
  $: name = String(identity?.display_name || identity?.username || '');

  async function confirm() {
    if (busy || (orphaned?.length && !heir)) return;
    busy = true;
    try {
      if (orphaned?.length) {
        // A deletion hands over every folder; a deactivation only those that would stay without guardian
        await apiPostData(fetch, `/identity/${identity!.id}/handover`, { to_identity_id: heir, scope: mode === 'delete' ? 'all' : 'orphaned', remove_from_source: mode === 'delete' });
      }
      await onConfirm();
      loadedFor = '';
    } catch (error: unknown) {
      reportUiError(error, 'The change failed.', `identity.${mode}`);
    } finally {
      busy = false;
    }
  }
</script>

<AppModal {open} onClose={() => { loadedFor = ''; onClose(); }} iconClass={mode === 'delete' ? 'bi bi-trash' : 'bi bi-pause-circle'}
  title={mode === 'delete' ? t('Delete the identity') : t('Disable the identity')} subtitle={name}>
  <div class="ld">
    <p>{mode === 'delete' ? t('They can no longer sign in to BornToShare; their requests and history stay.') : t('They can no longer sign in until enabled again.')}</p>
    {#if orphaned === null}
      <LoadingState skeleton="rows" rows={2} />
    {:else if orphaned.length}
      <InlineAlert tone="warning">{t('Only active guardian of {count} folder(s): without someone else, nobody but an administrator would validate their requests.', { count: orphaned.length })}</InlineAlert>
      <ul class="ld__list">
        {#each orphaned.slice(0, 8) as folder (folder.id)}<li><b>{folder.name}</b><small class="mono">{folder.path}</small></li>{/each}
        {#if orphaned.length > 8}<li class="ld__more">{t('+ {count} other(s)', { count: orphaned.length - 8 })}</li>{/if}
      </ul>
      <label class="ld__field">{mode === 'delete' ? t('Hand all their folders over to') : t('Hand these folders over to')}
        <select class="b2s-input" bind:value={heir}>
          <option value={0}>{t('Choose a person')}</option>
          {#each people as person (person.id)}<option value={Number(person.id)}>{person.display_name || person.username}{person.email ? '' : ` · ${t('no e-mail')}`}</option>{/each}
        </select>
      </label>
      {#if mode === 'disable'}<small class="ld__hint">{t('For an absence, prefer a backup guardian: the folders come back by themselves at its end.')}</small>{/if}
    {/if}
  </div>
  <svelte:fragment slot="footer">
    <button type="button" class="b2s-btn b2s-btn-secondary" on:click={() => { loadedFor = ''; onClose(); }}>{t('Cancel')}</button>
    <button type="button" class={`b2s-btn ${mode === 'delete' ? 'b2s-btn-danger' : 'b2s-btn-primary'}`} disabled={busy || orphaned === null || (orphaned.length > 0 && !heir)} on:click={confirm}>
      {orphaned?.length ? (mode === 'delete' ? t('Hand over and delete') : t('Hand over and disable')) : mode === 'delete' ? t('Delete') : t('Disable')}
    </button>
  </svelte:fragment>
</AppModal>

<style>
  .ld { display: flex; flex-direction: column; gap: 12px; }
  .ld p { margin: 0; }
  .ld__list { display: flex; flex-direction: column; gap: 4px; margin: 0; padding: 0; list-style: none; }
  .ld__list li { display: flex; flex-direction: column; padding: 6px 10px; border-radius: 8px; background: var(--b2s-color-surface-soft, #f6f7f9); }
  .ld__list small { color: var(--b2s-color-text-muted); }
  .ld__more { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .ld__field { display: flex; flex-direction: column; gap: 6px; font-size: var(--b2s-fs-sm); font-weight: 600; }
  .ld__hint { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .mono { font-family: var(--b2s-font-mono); font-size: var(--b2s-fs-xs); }
</style>
