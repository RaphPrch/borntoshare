<script lang="ts">
  import { t } from '$lib/i18n';
  import EntityActionGroup, { type EntityActionItem } from '$lib/components/entity/EntityActionGroup.svelte';

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

<header class="srh">
  <nav class="srh__crumbs" aria-label={t('Location')}>
    <span>{zoneLabel || t('Storage root')}</span>
    {#if endpointLabel && endpointLabel !== '—'}<i class="bi bi-chevron-right" aria-hidden="true"></i><span>{endpointLabel}</span>{/if}
  </nav>
  <div class="srh__row">
    <h1>{title}</h1>
    {#if statusLabel}
      <span class={`srh__pill is-${statusTone}`}><span aria-hidden="true"></span>{statusLabel}</span>
    {/if}
    <div class="srh__actions">
      <EntityActionGroup {actions} ariaLabel={t('Storage root actions')} />
    </div>
  </div>
  <code class="srh__path">{pathLabel}</code>
</header>

<style>
  .srh {
    display: grid;
    gap: 8px;
  }

  .srh__crumbs {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-xs);
  }

  .srh__crumbs i {
    font-size: 10px;
  }

  .srh__row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 12px;
  }

  h1 {
    margin: 0;
    font-size: var(--b2s-fs-page-title);
    font-weight: 700;
    letter-spacing: -0.01em;
    overflow-wrap: anywhere;
  }

  .srh__pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 3px 10px;
    border-radius: var(--b2s-radius-pill);
    font-size: var(--b2s-fs-xs);
    font-weight: 600;
  }

  .srh__pill span {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: currentColor;
  }

  .srh__pill.is-success { background: var(--b2s-color-success-soft); color: var(--b2s-color-success-strong); }
  .srh__pill.is-warning { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }
  .srh__pill.is-danger { background: var(--b2s-color-danger-soft); color: var(--b2s-color-danger-strong); }
  .srh__pill.is-neutral { background: var(--b2s-color-neutral-soft); color: var(--b2s-color-text-muted); }

  .srh__actions {
    margin-left: auto;
  }

  .srh__path {
    justify-self: start;
    max-width: 100%;
    padding: 3px 8px;
    border-radius: 6px;
    background: var(--b2s-color-neutral-soft);
    color: var(--b2s-color-text-soft);
    font-family: var(--b2s-font-mono);
    font-size: var(--b2s-fs-xs);
    overflow-wrap: anywhere;
  }
</style>
