<script lang="ts">
  import { t } from '$lib/i18n';
  import EntityActionGroup, { type EntityActionItem } from '$lib/components/entity/EntityActionGroup.svelte';
  import { toast } from '$lib/stores/toast';

  /**
   * Storage root header, as a card: folder icon, breadcrumb, name, one status pill, the path to copy, actions.
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

  async function copyPath() {
    try {
      await navigator.clipboard.writeText(pathLabel);
      toast.success(t('Path copied.'));
    } catch {
      toast.error(t('The path could not be copied.'));
    }
  }
</script>

<header class="srh">
  <span class="srh__icon" aria-hidden="true"><i class="bi bi-folder2-open"></i></span>
  <div class="srh__main">
    <nav class="srh__crumbs" aria-label={t('Location')}>
      <span>{zoneLabel || t('Storage root')}</span>
      {#if endpointLabel && endpointLabel !== '—'}<i class="bi bi-chevron-right" aria-hidden="true"></i><span>{endpointLabel}</span>{/if}
    </nav>
    <div class="srh__title">
      <h1>{title}</h1>
      {#if statusLabel}<span class={`srh__pill is-${statusTone}`}><span aria-hidden="true"></span>{statusLabel}</span>{/if}
    </div>
    {#if pathLabel && pathLabel !== '—'}
      <span class="srh__path">
        <code title={pathLabel}>{pathLabel}</code>
        <button type="button" on:click={copyPath} aria-label={t('Copy the path')}><i class="bi bi-copy" aria-hidden="true"></i>{t('Copy')}</button>
      </span>
    {/if}
  </div>
  <div class="srh__actions"><EntityActionGroup {actions} ariaLabel={t('Storage root actions')} /></div>
</header>

<style>
  .srh { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; gap: 16px; align-items: center; padding: 18px 20px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); box-shadow: var(--b2s-shadow-sm); }
  .srh__icon { display: grid; place-items: center; width: 48px; height: 48px; border-radius: 14px; background: var(--b2s-accent-soft); color: var(--b2s-color-success-strong); font-size: 22px; }
  .srh__main { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
  .srh__crumbs { display: flex; align-items: center; gap: 6px; color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-sm); }
  .srh__crumbs i { font-size: 10px; }
  .srh__title { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
  .srh__title h1 { margin: 0; font-size: var(--b2s-fs-page-title, 24px); font-weight: 600; letter-spacing: -0.01em; overflow-wrap: anywhere; }
  .srh__pill { display: inline-flex; align-items: center; gap: 6px; padding: 2px 10px; border-radius: var(--b2s-radius-pill); font-size: var(--b2s-fs-xs); font-weight: 500; background: var(--b2s-color-neutral-soft); color: var(--b2s-color-text-muted); }
  .srh__pill span { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
  .srh__pill.is-success { background: var(--b2s-color-success-soft); color: var(--b2s-color-success-strong); }
  .srh__pill.is-warning { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }
  .srh__pill.is-danger { background: var(--b2s-color-danger-soft); color: var(--b2s-color-danger-strong); }
  .srh__path { display: inline-flex; align-items: center; gap: 6px; align-self: flex-start; max-width: 100%; padding: 3px 4px 3px 9px; border-radius: var(--b2s-radius-sm); background: var(--b2s-color-neutral-soft); }
  .srh__path code { min-width: 0; padding: 0; background: none; color: inherit; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-family: var(--b2s-font-mono); font-size: var(--b2s-fs-xs); }
  .srh__path button { display: inline-flex; align-items: center; gap: 4px; flex: none; padding: 1px 8px; border: 0; border-radius: 6px; background: var(--b2s-color-surface); font-size: var(--b2s-fs-xs); cursor: pointer; }
  .srh__actions { align-self: start; }
</style>
