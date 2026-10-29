<script lang="ts">
  import { t } from '$lib/i18n';
  import { toast } from '$lib/stores/toast';
  import { reportUiError } from '$lib/errors';
  import ConfirmActionModal from '$lib/components/ui/ConfirmActionModal.svelte';
  import { CATEGORIES } from '$lib/utils/infrastructure';
  import {
    createInfraService,
    deleteInfraService,
    listInfraServices,
    updateInfraService,
    type InfraService,
    type ServiceInput
  } from '$lib/api/infrastructure';

  export let services: InfraService[] = [];

  const CATEGORY_OPTIONS = CATEGORIES.filter((c) => !['worker', 'directory'].includes(c.key));
  const empty = (): ServiceInput => ({ label: '', category: 'custom', check_kind: 'http', target: '', is_enabled: true });

  let draft: ServiceInput = empty();
  let editingId: number | null = null;
  let adding = false;
  let saving = false;
  let removing: InfraService | null = null;

  $: draftError = (() => {
    const target = draft.target.trim();
    if (!draft.label.trim() || !target) return null;
    if (draft.check_kind === 'http' && !/^https?:\/\//.test(target)) return t('An http:// or https:// URL is expected');
    if (draft.check_kind === 'tcp' && !/^[^\s/]+:\d{1,5}$/.test(target)) return t('host:port is expected');
    return null;
  })();
  $: draftValid = !!draft.label.trim() && !!draft.target.trim() && !draftError;

  function categoryLabel(key: string) {
    return CATEGORIES.find((c) => c.key === key)?.label() ?? key;
  }

  function startAdd() {
    editingId = null;
    draft = empty();
    adding = true;
  }

  function startEdit(service: InfraService) {
    adding = false;
    editingId = service.id;
    draft = { label: service.label, category: service.category, check_kind: service.check_kind, target: service.target, is_enabled: service.is_enabled };
  }

  function cancel() {
    adding = false;
    editingId = null;
  }

  async function reload() {
    services = await listInfraServices(fetch);
  }

  async function submit() {
    if (!draftValid || saving) return;
    saving = true;
    try {
      if (editingId !== null) await updateInfraService(fetch, editingId, { ...draft, target: draft.target.trim() });
      else await createInfraService(fetch, { ...draft, target: draft.target.trim() });
      toast.success(editingId !== null ? t('Component updated.') : t('Component added: checked at the next health check.'));
      cancel();
      await reload();
    } catch (e) {
      reportUiError(e, t('Unable to save the component.'), 'infrastructure.services.save');
    } finally {
      saving = false;
    }
  }

  async function toggle(service: InfraService) {
    try {
      await updateInfraService(fetch, service.id, { label: service.label, category: service.category, check_kind: service.check_kind, target: service.target, is_enabled: !service.is_enabled });
      await reload();
    } catch (e) {
      reportUiError(e, t('Unable to update the component.'), 'infrastructure.services.toggle');
    }
  }

  async function confirmRemove() {
    const service = removing;
    removing = null;
    if (!service) return;
    try {
      await deleteInfraService(fetch, service.id);
      await reload();
      toast.success(t('Component removed.'));
    } catch (e) {
      reportUiError(e, t('Unable to remove the component.'), 'infrastructure.services.remove');
    }
  }
</script>

<div class="toolbar">
  <p>{t('Checked from a worker at every health check. Directories, file servers, workers and Keycloak are added automatically.')}</p>
  <button type="button" class="b2s-btn b2s-btn-primary" on:click={startAdd} disabled={adding}>
    <i class="bi bi-plus-lg" aria-hidden="true"></i>{t('Add a component')}
  </button>
</div>

<div class="b2s-table-wrap">
  <table class="table align-middle svc">
    <thead>
      <tr>
        <th>{t('Component')}</th>
        <th>{t('Category')}</th>
        <th>{t('Check')}</th>
        <th>{t('Target')}</th>
        <th class="center">{t('Monitored')}</th>
        <th class="right"><span class="visually-hidden">{t('Actions')}</span></th>
      </tr>
    </thead>
    <tbody>
      {#each services as service (service.id)}
        {#if editingId === service.id}
          <tr class="editing">
            <td><input class="cell-input" bind:value={draft.label} aria-label={t('Name')} /></td>
            <td>
              <select class="b2s-select" bind:value={draft.category} aria-label={t('Category')}>
                {#each CATEGORY_OPTIONS as option (option.key)}<option value={option.key}>{option.label()}</option>{/each}
              </select>
            </td>
            <td>
              <select class="b2s-select" bind:value={draft.check_kind} aria-label={t('Check')}>
                <option value="http">HTTP(S)</option>
                <option value="tcp">TCP</option>
              </select>
            </td>
            <td>
              <input class="cell-input mono" bind:value={draft.target} aria-label={t('Target')} spellcheck="false" />
              {#if draftError}<small class="err">{draftError}</small>{/if}
            </td>
            <td class="center"><input type="checkbox" class="cap-switch" bind:checked={draft.is_enabled} aria-label={t('Monitored')} /></td>
            <td class="right nowrap">
              <button type="button" class="b2s-btn b2s-btn-ghost b2s-btn-sm" on:click={cancel}>{t('Cancel')}</button>
              <button type="button" class="b2s-btn b2s-btn-primary b2s-btn-sm" on:click={submit} disabled={!draftValid || saving}>{t('Save')}</button>
            </td>
          </tr>
        {:else}
          <tr class:is-off={!service.is_enabled}>
            <td>
              <strong>{service.label}</strong>
              {#if service.is_builtin}<span class="tag">{t('Platform')}</span>{/if}
            </td>
            <td>{categoryLabel(service.category)}</td>
            <td><span class="kind">{service.check_kind === 'http' ? 'HTTP(S)' : 'TCP'}</span></td>
            <td class="mono target" title={service.target}>{service.target}</td>
            <td class="center">
              <input type="checkbox" class="cap-switch" checked={service.is_enabled} on:change={() => toggle(service)} aria-label={t('Monitored')} />
            </td>
            <td class="right nowrap">
              <button type="button" class="b2s-btn b2s-btn-ghost b2s-btn-sm" on:click={() => startEdit(service)} aria-label={t('Edit')}>
                <i class="bi bi-pencil" aria-hidden="true"></i>
              </button>
              {#if !service.is_builtin}
                <button type="button" class="b2s-btn b2s-btn-ghost b2s-btn-sm" on:click={() => (removing = service)} aria-label={t('Remove')}>
                  <i class="bi bi-trash3" aria-hidden="true"></i>
                </button>
              {/if}
            </td>
          </tr>
        {/if}
      {/each}
      {#if adding}
        <tr class="editing">
          <td><input class="cell-input" bind:value={draft.label} placeholder={t('Reverse proxy')} aria-label={t('Name')} /></td>
          <td>
            <select class="b2s-select" bind:value={draft.category} aria-label={t('Category')}>
              {#each CATEGORY_OPTIONS as option (option.key)}<option value={option.key}>{option.label()}</option>{/each}
            </select>
          </td>
          <td>
            <select class="b2s-select" bind:value={draft.check_kind} aria-label={t('Check')}>
              <option value="http">HTTP(S)</option>
              <option value="tcp">TCP</option>
            </select>
          </td>
          <td>
            <input class="cell-input mono" bind:value={draft.target} placeholder={draft.check_kind === 'http' ? 'https://proxy.example.com/health' : 'nas01.example.com:445'} aria-label={t('Target')} spellcheck="false" />
            {#if draftError}<small class="err">{draftError}</small>{/if}
          </td>
          <td class="center"><input type="checkbox" class="cap-switch" bind:checked={draft.is_enabled} aria-label={t('Monitored')} /></td>
          <td class="right nowrap">
            <button type="button" class="b2s-btn b2s-btn-ghost b2s-btn-sm" on:click={cancel}>{t('Cancel')}</button>
            <button type="button" class="b2s-btn b2s-btn-primary b2s-btn-sm" on:click={submit} disabled={!draftValid || saving}>{t('Add')}</button>
          </td>
        </tr>
      {/if}
    </tbody>
  </table>
</div>

<ConfirmActionModal
  open={!!removing}
  title={t('Remove the component')}
  subtitle={t('{name} is no longer checked.', { name: removing?.label ?? '' })}
  confirmLabel={t('Remove')}
  onConfirm={confirmRemove}
  onClose={() => (removing = null)}
/>

<style>
  .toolbar {
    display: flex;
    align-items: center;
    gap: 14px;
    justify-content: space-between;
    margin-bottom: 12px;
  }

  .toolbar p {
    margin: 0;
    color: var(--b2s-color-text-soft);
    font-size: var(--b2s-fs-sm);
  }

  .svc td {
    font-size: var(--b2s-fs-sm);
    vertical-align: middle;
  }

  .svc tr.is-off td {
    color: var(--b2s-color-text-faint);
  }

  .mono {
    font-family: var(--b2s-font-mono);
  }

  .target {
    max-width: 320px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .tag {
    margin-left: 6px;
    padding: 1px 7px;
    border-radius: var(--b2s-radius-pill);
    background: var(--b2s-color-primary-soft);
    color: #3730a3;
    font-size: var(--b2s-fs-xs);
  }

  .kind {
    padding: 2px 8px;
    border-radius: var(--b2s-radius-pill);
    background: var(--b2s-color-neutral-soft);
    font-size: var(--b2s-fs-xs);
    color: var(--b2s-color-text-strong);
  }

  .center {
    text-align: center;
  }

  .right {
    text-align: right;
  }

  .nowrap {
    white-space: nowrap;
  }

  .editing td {
    background: #f8faff;
  }

  .cell-input {
    width: 100%;
    height: 34px;
    padding: 0 10px;
    border: 1px solid var(--b2s-color-border-soft);
    border-radius: var(--b2s-radius-sm);
    font-size: var(--b2s-fs-sm);
  }

  .err {
    display: block;
    color: var(--b2s-color-danger-strong);
    font-size: var(--b2s-fs-xs);
    margin-top: 2px;
  }





  @media (max-width: 720px) {
    .toolbar {
      flex-direction: column;
      align-items: stretch;
    }
  }
</style>
