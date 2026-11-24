<script lang="ts">
  import { fivesEnabled, governanceEnabled } from '$lib/utils/features';
  

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
    onDeleteRoot?: () => void;
    onToggleInheritance?: () => void;
    onDeleteFolder?: () => void;
    onCreateSubfolder?: () => void;
    /** v2: measure the folder and scan its sensitivity from the header (administrators) */
    onMeasure?: (() => void) | null;
    onScanSensitivity?: (() => void) | null;
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
    onDeleteRoot = () => {},
    onToggleInheritance = () => {},
    onDeleteFolder = () => {},
    onCreateSubfolder = () => {},
    onMeasure = null,
    onScanSensitivity = null
  }: Props = $props();

  let disabled = $derived(!selectedStorageRootId);
  let actions: EntityActionItem[] = $state([]);
  $effect.pre(() => {
    actions = [
      ...(isAdmin && onMeasure ? [{ key: 'measure', label: t('Measure'), icon: 'bi-rulers', variant: 'secondary' as const, disabled, onClick: onMeasure }] : []),
      // The sensitivity scan comes with the 5S module
      ...(isAdmin && onScanSensitivity && $fivesEnabled ? [{ key: 'sensitivity', label: t('Scan the sensitivity'), icon: 'bi-shield-lock', variant: 'secondary' as const, disabled, onClick: onScanSensitivity }] : []),
      {
        key: 'probe',
        label: rootProbeBusy ? t('Reading…') : t('Read the ACL'),
        icon: rootProbeBusy ? 'bi-arrow-repeat sed-spin' : 'bi-arrow-clockwise',
        variant: 'secondary',
        disabled: disabled || rootProbeBusy,
        title: t('Test the folder and read its NTFS permissions on the file server'),
        onClick: onRunRootProbe
      },
      // Access requests, inheritance and sub-folders belong to the governance (not in a 5S-only installation)
      ...($governanceEnabled ? [{ key: 'access-request', label: t('Request access'), icon: 'bi-plus-lg', variant: 'primary' as const, disabled, onClick: onNewAccessRequest }] : []),
      ...(isAdmin
        ? ([
            ...($governanceEnabled ? [{
              key: 'inheritance',
              label: inheritanceBroken ? t('Restore the inheritance') : t('Break the inheritance'),
              icon: inheritanceBroken ? 'bi-link-45deg' : 'bi-scissors',
              overflow: true,
              disabled: disabled || inheritanceBroken === null,
              title: inheritanceBroken === null ? t('Read the ACL first') : undefined,
              onClick: onToggleInheritance
            },
            { key: 'subfolder', label: t('New sub-folder'), icon: 'bi-folder-plus', overflow: true, disabled, onClick: onCreateSubfolder }] : []),
            // Audit evidence of this folder over the last 12 months (ZIP built by core-service)
            { key: 'evidence', label: t('Audit evidence pack'), icon: 'bi-file-earmark-zip', overflow: true, disabled: !selectedStorageRootId,
              onClick: () => window.location.assign(`/api/activity/evidence-pack?${new URLSearchParams({ root_id: String(selectedStorageRootId),
                since: new Date(Date.now() - 365 * 86_400_000).toISOString().slice(0, 10), until: new Date().toISOString().slice(0, 10) })}`) },
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
