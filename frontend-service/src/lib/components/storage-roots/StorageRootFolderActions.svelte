<script context="module" lang="ts">
  export type FolderActionKind = 'inheritance' | 'delete' | 'subfolder';
  /** The folder an action applies to: the selected storage root, or the one right-clicked in the explorer */
  export type FolderActionTarget = { id: number; name: string; path: string; inheritanceBroken: boolean | null };
</script>

<script lang="ts">
  import { tick } from 'svelte';
  import ConfirmActionModal from '$lib/components/ui/ConfirmActionModal.svelte';
  import { t } from '$lib/i18n';
  import { reportUiError } from '$lib/errors';
  import { toast } from '$lib/stores/toast';
  import { createSubfolder, deleteStorageRootFolder, setFolderInheritance } from '$lib/api/storage-root-permissions';

  /**
   * Operations of the worker on the folder of a storage root, on the file server (platform admins):
   * break / restore the NTFS inheritance, delete the folder, create a sub-folder.
   */
  export let kind: FolderActionKind | null = null;
  export let target: FolderActionTarget | null = null;
  export let onClose: () => void = () => {};
  /** The inheritance changed: the page reads the ACL again */
  export let onInheritanceChanged: (rootId: number) => void = () => {};
  export let onDeleted: (rootId: number) => void = () => {};
  /** A sub-folder was created; rootId is its storage root when it was registered */
  export let onSubfolderCreated: (rootId: number | null) => void = () => {};

  let busy = false;
  let folderName = '';
  let register = true;
  let nameError = '';

  let nameInput: HTMLInputElement | null = null;
  $: if (kind !== 'subfolder') {
    folderName = '';
    nameError = '';
    register = true;
  } else {
    void focusName();
  }
  // The right click leaves the focus on the explorer row: put it in the name field
  async function focusName() {
    await tick();
    await tick();
    nameInput?.focus();
  }

  const FORBIDDEN = /[\\/:*?"<>|\u0000-\u001f]/;
  function validateName(name: string): string {
    if (!name || name === '.' || name === '..') return t('Type the name of the folder.');
    if (FORBIDDEN.test(name)) return t('These characters are refused by Windows: \\ / : * ? " < > |');
    if (name !== name.trim() || name.endsWith('.')) return t('The name cannot start or end with a space, nor end with a dot.');
    return '';
  }

  async function run(action: () => Promise<void>, failure: string, scope: string) {
    busy = true;
    try {
      await action();
    } catch (error: unknown) {
      reportUiError(error, failure, scope);
    } finally {
      busy = false;
    }
  }

  async function confirmInheritance() {
    const root = target;
    if (!root) return;
    const mode = root.inheritanceBroken ? 'restore' : 'break';
    await run(async () => {
      await setFolderInheritance(fetch, root.id, mode);
      toast.success(mode === 'break' ? t('Inheritance broken on the file server.') : t('Inheritance restored on the file server.'));
      onClose();
      onInheritanceChanged(root.id);
    }, t('The file server did not change the inheritance.'), 'storage-root.inheritance');
  }

  async function confirmDelete() {
    const root = target;
    if (!root) return;
    await run(async () => {
      await deleteStorageRootFolder(fetch, root.id, root.name);
      toast.success(t('Folder {name} deleted from the file server.', { name: root.name }));
      onClose();
      onDeleted(root.id);
    }, t('The folder was not deleted.'), 'storage-root.delete-folder');
  }

  async function confirmSubfolder() {
    const root = target;
    nameError = validateName(folderName);
    if (!root || nameError) return;
    await run(async () => {
      const created = await createSubfolder(fetch, root.id, folderName, register);
      toast.success(t('Folder {name} created on the file server.', { name: folderName }));
      onClose();
      onSubfolderCreated(created?.storage_root_id ?? null);
    }, t('The folder was not created.'), 'storage-root.subfolder');
  }
</script>

<ConfirmActionModal
  open={kind === 'inheritance' && Boolean(target)}
  {onClose}
  onConfirm={confirmInheritance}
  {busy}
  severity="warning"
  title={target?.inheritanceBroken
    ? t('Restore the inheritance of {name}?', { name: target?.name ?? '' })
    : t('Break the inheritance of {name}?', { name: target?.name ?? '' })}
  subtitle={t('Are you sure?')}
  confirmLabel={target?.inheritanceBroken ? t('Restore the inheritance') : t('Break the inheritance')}
  confirmVariant="warning"
/>

<ConfirmActionModal
  open={kind === 'delete' && Boolean(target)}
  {onClose}
  onConfirm={confirmDelete}
  {busy}
  title={t('Delete the folder {name} from the file server?', { name: target?.name ?? '' })}
  subtitle={target?.path ?? ''}
  impactItems={[
    t('The folder and everything in it are deleted on the file server. This cannot be undone.'),
    t('The storage root is removed from BornToShare.'),
    t('Refused while an access is in force or a request is pending.')
  ]}
  requireTextConfirm={true}
  requiredText={target?.name ?? ''}
  textConfirmLabel={t('Type the name of the storage root to confirm')}
  textConfirmPlaceholder={target?.name ?? ''}
  confirmLabel={t('Delete the folder')}
  confirmVariant="danger"
/>

<ConfirmActionModal
  open={kind === 'subfolder' && Boolean(target)}
  {onClose}
  onConfirm={confirmSubfolder}
  {busy}
  role="dialog"
  severity="warning"
  title={t('New folder in {name}', { name: target?.name ?? '' })}
  subtitle={target?.path ?? ''}
  confirmLabel={t('Create the folder')}
  confirmVariant="primary"
>
  <div class="sub">
    <label class="sub__field">
      <span>{t('Folder name')}</span>
      <input bind:this={nameInput} class="b2s-form-control" type="text" bind:value={folderName} maxlength="255" autocomplete="off"
        aria-invalid={Boolean(nameError)} on:input={() => (nameError = '')} />
      {#if nameError}<small class="sub__error">{nameError}</small>{/if}
      {#if folderName && !nameError}<small class="sub__path">{target?.path}\{folderName}</small>{/if}
    </label>
    <label class="sub__check">
      <input type="checkbox" class="cap-switch" bind:checked={register} />
      <span>
        <strong>{t('Govern it in BornToShare')}</strong>
        <small>{t('A storage root is created for it, under {name}, with its guardians and tags.', { name: target?.name ?? '' })}</small>
      </span>
    </label>
  </div>
</ConfirmActionModal>

<style>
  .sub {
    display: grid;
    gap: 16px;
  }

  .sub__field {
    display: grid;
    gap: 6px;
  }

  .sub__field > span {
    font-weight: 600;
  }

  .sub__error {
    color: var(--b2s-color-danger-strong);
  }

  .sub__path {
    color: var(--b2s-color-text-muted);
    font-family: var(--b2s-font-mono);
    font-size: var(--b2s-fs-xs);
    overflow-wrap: anywhere;
  }

  .sub__check {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    cursor: pointer;
  }

  .sub__check strong,
  .sub__check small {
    display: block;
  }

  .sub__check small {
    color: var(--b2s-color-text-muted);
  }
</style>
