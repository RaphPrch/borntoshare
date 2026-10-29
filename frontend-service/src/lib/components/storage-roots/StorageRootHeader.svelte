<script lang="ts">
  import { t } from '$lib/i18n';
  import EntityPageHeader from '$lib/components/entity/EntityPageHeader.svelte';
  import type { EntityActionItem } from '$lib/components/entity/EntityActionGroup.svelte';

  /**
   * Storage root header, without a card: breadcrumb, name, one status pill, actions, UNC path.
   * Folder operations on the file server (inheritance, deletion) are platform admin actions of the overflow menu.
   */
  type StatusTone = 'success' | 'warning' | 'danger' | 'neutral';

  export let title = t('Storage root');
  export let zoneLabel = '';
  export let endpointLabel = '';
  export let pathLabel = '—';
  export let statusLabel = '';
  export let statusTone: StatusTone = 'neutral';
  export let rootProbeBusy = false;
  export let selectedStorageRootId: number | null = null;
  export let isAdmin = false;
  /** null while the ACL has never been read */
  export let inheritanceBroken: boolean | null = null;
  export let onRunRootProbe: () => void = () => {};
  export let onNewAccessRequest: () => void = () => {};
  export let onEditRoot: () => void = () => {};
  export let onDeleteRoot: () => void = () => {};
  export let onToggleInheritance: () => void = () => {};
  export let onDeleteFolder: () => void = () => {};
  export let onCreateSubfolder: () => void = () => {};

  $: disabled = !selectedStorageRootId;
  let actions: EntityActionItem[] = [];
  $: actions = [
    {
      key: 'probe',
      label: rootProbeBusy ? t('Reading…') : t('Read the ACL'),
      icon: rootProbeBusy ? 'bi-arrow-repeat sed-spin' : 'bi-arrow-clockwise',
      variant: 'secondary',
      disabled: disabled || rootProbeBusy,
      title: t('Test the folder and read its NTFS permissions on the file server'),
      onClick: onRunRootProbe
    },
    { key: 'access-request', label: t('Request access'), icon: 'bi-plus-lg', variant: 'primary', disabled, onClick: onNewAccessRequest },
    { key: 'edit', label: t('Edit storage root'), icon: 'bi-pencil-square', overflow: true, disabled, onClick: onEditRoot },
    ...(isAdmin
      ? ([
          {
            key: 'inheritance',
            label: inheritanceBroken ? t('Restore the inheritance') : t('Break the inheritance'),
            icon: inheritanceBroken ? 'bi-link-45deg' : 'bi-scissors',
            overflow: true,
            disabled: disabled || inheritanceBroken === null,
            title: inheritanceBroken === null ? t('Read the ACL first') : undefined,
            onClick: onToggleInheritance
          },
          { key: 'subfolder', label: t('New sub-folder'), icon: 'bi-folder-plus', overflow: true, disabled, onClick: onCreateSubfolder },
          { key: 'delete', label: t('Remove from BornToShare'), icon: 'bi-x-circle', overflow: true, disabled, onClick: onDeleteRoot },
          { key: 'delete-folder', label: t('Delete the folder from the server'), icon: 'bi-trash', variant: 'danger', overflow: true, disabled, onClick: onDeleteFolder }
        ] satisfies EntityActionItem[])
      : [])
  ];
</script>

<EntityPageHeader
  crumbs={[zoneLabel || t('Storage root'), ...(endpointLabel && endpointLabel !== '—' ? [endpointLabel] : [])]}
  {title}
  {statusLabel}
  {statusTone}
  code={pathLabel}
  {actions}
  actionsAriaLabel={t('Storage root actions')}
/>
