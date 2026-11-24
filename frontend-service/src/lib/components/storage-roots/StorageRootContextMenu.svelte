<script module lang="ts">
  /** Other entries of the menu, handled by the page: the parts of the folder sheet */
  export type FolderMenuExtra = 'tags' | 'guardians' | 'quota' | 'permissions';
</script>

<script lang="ts">
  import { t } from '$lib/i18n';
  import { goto } from '$app/navigation';
  import ContextMenu, { type ContextMenuItem } from '$lib/components/ui/ContextMenu.svelte';
  import { fivesEnabled, governanceEnabled } from '$lib/utils/features';
  import type { StorageRootRow } from '$lib/utils/storage-roots';
  import type { FolderActionKind } from '$lib/components/storage-roots/StorageRootFolderActions.svelte';

  interface Props {
    /** Right-click menu of a storage root in the explorer: open it, and the operations on its folder on the file server. */
    row?: StorageRootRow | null;
    at?: any;
    onClose?: () => void;
    onAction?: (kind: FolderActionKind, row: StorageRootRow) => void;
    /** Platform administrators: the operations on the folder of the file server; everyone can request an access */
    canManage?: boolean;
    /** Tags, guardians, quota, permissions of the folder (absent: those entries are not shown) */
    onExtra?: ((key: FolderMenuExtra, row: StorageRootRow) => void) | null;
  }

  let {
    row = null,
    at = { x: 0, y: 0 },
    onClose = () => {},
    onAction = () => {},
    canManage = true,
    onExtra = null
  }: Props = $props();

  let broken = $derived(row?.inheritance_broken);
  let items = $derived(row
    ? [
        ...($fivesEnabled ? [{ key: 'explore', label: t('Explore the content'), icon: 'bi-columns-gap',
          run: (target: StorageRootRow) => void goto(`/five-s/explore/${Number(target?.storage_root_id ?? 0)}`) }] : []),
        ...(onExtra && $governanceEnabled ? [{ key: 'permissions', label: t('Permissions and who reaches it'), icon: 'bi-shield-lock', separated: true,
          run: (target: StorageRootRow) => onExtra?.('permissions', target) }] : []),
        ...(onExtra ? [
          { key: 'tags', label: t('Tags…'), icon: 'bi-tags', run: (target: StorageRootRow) => onExtra?.('tags', target) },
          ...($governanceEnabled ? [{ key: 'guardians', label: t('Guardians…'), icon: 'bi-person-check', run: (target: StorageRootRow) => onExtra?.('guardians', target) }] : []),
          { key: 'quota', label: t('Quota…'), icon: 'bi-speedometer', run: (target: StorageRootRow) => onExtra?.('quota', target) }
        ] : []),
        ...($governanceEnabled ? [{
          key: 'request',
          label: t('Request access'),
          icon: 'bi-key',
          run: (target: StorageRootRow) => void goto(`/access-requests/new?root=${Number(target?.storage_root_id ?? 0)}`)
        }] : []),
        ...(canManage && $governanceEnabled ? [{
          key: 'inheritance',
          label: broken ? t('Restore the inheritance') : t('Break the inheritance'),
          icon: broken ? 'bi-diagram-3' : 'bi-scissors',
          disabled: broken == null,
          hint: broken == null ? t('Read the ACL first') : '',
          run: (target: StorageRootRow) => onAction('inheritance', target)
        }] : []),
        ...(canManage ? [
        // The sensitivity scan comes with the 5S module
        ...($fivesEnabled ? [{ key: 'sensitivity', label: t('Scan the sensitivity'), icon: 'bi-shield-lock', run: (target: StorageRootRow) => onAction('sensitivity', target) }] : []),
        { key: 'measure', label: t('Measure the folder'), icon: 'bi-rulers', run: (target: StorageRootRow) => onAction('measure', target) },
        ...($governanceEnabled ? [{ key: 'subfolder', label: t('New sub-folder'), icon: 'bi-folder-plus', run: (target: StorageRootRow) => onAction('subfolder', target) }] : []),
        { key: 'delete', label: t('Delete the folder from the server'), icon: 'bi-trash', danger: true, run: (target: StorageRootRow) => onAction('delete', target) }] : [])
      ]
    : []);
  // The shared menu draws it; the delete entry stands apart
  let menuItems = $derived(items.map(({ run: _run, ...item }) => ({ ...item, separated: item.key === 'delete' || Boolean((item as { separated?: boolean }).separated) }) as ContextMenuItem));

  function pick(key: string) {
    // The target first: closing the menu clears `row` (the parent owns it)
    const target = row;
    const item = items.find((entry) => entry.key === key);
    if (target && item) item.run(target);
  }
</script>

<ContextMenu open={Boolean(row)} title={String(row?.storage_root_name ?? row?.storage_root_code ?? '')} subtitle={String(row?.root_path ?? '')}
  items={menuItems} {at} {onClose} onPick={pick} />
