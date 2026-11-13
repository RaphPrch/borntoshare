<script module lang="ts">
  export type FolderActionKind = 'inheritance' | 'delete' | 'subfolder' | 'sensitivity' | 'measure';
  /** The folder an action applies to: the selected storage root, or the one right-clicked in the explorer */
  export type FolderActionTarget = { id: number; name: string; path: string; inheritanceBroken: boolean | null };
</script>

<script lang="ts">
  import { run as run_1 } from 'svelte/legacy';

  import { tick } from 'svelte';
  import ConfirmActionModal from '$lib/components/ui/ConfirmActionModal.svelte';
  import { t } from '$lib/i18n';
  import { reportUiError } from '$lib/errors';
  import { toast } from '$lib/stores/toast';
  import { createSubfolder, deleteStorageRootFolder, setFolderInheritance } from '$lib/api/storage-root-permissions';

  
  
  
  interface Props {
    /**
   * Operations of the worker on the folder of a storage root, on the file server (platform admins):
   * break / restore the NTFS inheritance, delete the folder, create a sub-folder.
   */
    kind?: FolderActionKind | null;
    target?: FolderActionTarget | null;
    onClose?: () => void;
    /** The inheritance changed: the page reads the ACL again */
    onInheritanceChanged?: (rootId: number) => void;
    onDeleted?: (rootId: number) => void;
    /** A sub-folder was created; rootId is its storage root when it was registered */
    onSubfolderCreated?: (rootId: number | null) => void;
  }

  let {
    kind = null,
    target = null,
    onClose = () => {},
    onInheritanceChanged = () => {},
    onDeleted = () => {},
    onSubfolderCreated = () => {}
  }: Props = $props();

  let busy = $state(false);
  let folderName = $state('');
  let register = $state(true);
  let nameError = $state('');

  let nameInput: HTMLInputElement | null = $state(null);
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

  // What each change does on the file server (checked on a lab folder and a sub-folder: break then restore)
  const RESTORE_IMPACT = () => [
    t('The folder receives the rights of its parent folder again: whoever reaches the parent reaches this folder too.'),
    t('The explicit rights of the folder stay; the copies made when the inheritance was broken repeat the inherited rights and are removed (no right changes).'),
    t('The inherited rights that BornToShare does not manage come back as gaps in Monitoring.'),
    t('Only this folder changes: its existing sub-folders keep their current rights.'),
    t('Applied at once on the file server; BornToShare then reads the rights of the folder again.')
  ];
  const BREAK_IMPACT = () => [
    t('The rights inherited from the parent folder are copied as explicit rights: nobody loses access.'),
    t('Later changes on the parent folder no longer apply to this folder.'),
    t('Only this folder changes: its existing sub-folders keep their current rights.'),
    t('Applied at once on the file server; BornToShare then reads the rights of the folder again.')
  ];

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
  run_1(() => {
    if (kind !== 'subfolder') {
      folderName = '';
      nameError = '';
      register = true;
    } else {
      void focusName();
    }
  });
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
  subtitle={target?.path ?? ''}
  impactItems={target?.inheritanceBroken ? RESTORE_IMPACT() : BREAK_IMPACT()}
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
      <input bind:this={nameInput} class="b2s-input" type="text" bind:value={folderName} maxlength="255" autocomplete="off"
        aria-invalid={Boolean(nameError)} oninput={() => (nameError = '')} />
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
