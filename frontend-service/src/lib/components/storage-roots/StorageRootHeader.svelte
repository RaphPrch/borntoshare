<script lang="ts">
  

  import { t } from '$lib/i18n';
  import EntityHeroCard from '$lib/components/entity/EntityHeroCard.svelte';
  import type { EntityActionItem } from '$lib/components/entity/EntityActionGroup.svelte';

  /**
   * Storage root header, as a card: folder icon, breadcrumb, name, one status pill, the path to copy, actions.
   * Folder operations on the file server (inheritance, deletion) are platform admin actions of the overflow menu.
   */
  type StatusTone = 'success' | 'warning' | 'danger' | 'neutral';

  
  interface Props {
    title?: any;
    zoneLabel?: string;
    endpointLabel?: string;
    pathLabel?: string;
    statusLabel?: string;
    statusTone?: StatusTone;
    rootProbeBusy?: boolean;
    selectedStorageRootId?: number | null;
    isAdmin?: boolean;
    /** null while the ACL has never been read */
    inheritanceBroken?: boolean | null;
    onRunRootProbe?: () => void;
    onNewAccessRequest?: () => void;
    onEditRoot?: () => void;
    onDeleteRoot?: () => void;
    onToggleInheritance?: () => void;
    onDeleteFolder?: () => void;
    onCreateSubfolder?: () => void;
  }

  let {
    title = t('Storage root'),
    zoneLabel = '',
    endpointLabel = '',
    pathLabel = '—',
    statusLabel = '',
    statusTone = 'neutral',
    rootProbeBusy = false,
    selectedStorageRootId = null,
    isAdmin = false,
    inheritanceBroken = null,
    onRunRootProbe = () => {},
    onNewAccessRequest = () => {},
    onEditRoot = () => {},
    onDeleteRoot = () => {},
    onToggleInheritance = () => {},
    onDeleteFolder = () => {},
    onCreateSubfolder = () => {}
  }: Props = $props();

  let disabled = $derived(!selectedStorageRootId);
  let actions: EntityActionItem[] = $state([]);
  $effect.pre(() => {
    actions = [
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
  });

</script>

<EntityHeroCard
  icon="bi-folder2-open"
  iconTone="green"
  crumbs={[zoneLabel || t('Storage root'), ...(endpointLabel && endpointLabel !== '—' ? [endpointLabel] : [])]}
  {title}
  {statusLabel}
  {statusTone}
  path={pathLabel && pathLabel !== '—' ? pathLabel : ''}
  {actions}
  actionsAriaLabel={t('Storage root actions')}
/>
