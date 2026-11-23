<script lang="ts">
  import { fivesEnabled, governanceEnabled } from '$lib/utils/features';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import { t } from '$lib/i18n';
  import StorageRootHeader from '$lib/components/storage-roots/StorageRootHeader.svelte';
  import StorageRootTiles from '$lib/components/storage-roots/StorageRootTiles.svelte';
  import StorageRootTodo from '$lib/components/storage-roots/StorageRootTodo.svelte';
  import StorageRootOverview from '$lib/components/storage-roots/StorageRootOverview.svelte';
  import StorageRootPermissions from '$lib/components/storage-roots/permissions/StorageRootPermissions.svelte';
  import ActivityTimeline from '$lib/components/activity/ActivityTimeline.svelte';
  import { presentErrorMessage, toAppError } from '$lib/errors';
  import { getStorageRootPermissions, type StorageRootPermissionsData } from '$lib/api/storage-root-permissions';
  import type { FolderActionKind } from '$lib/components/storage-roots/StorageRootFolderActions.svelte';

  /**
   * Sheet of a folder (v2): its identity card, its actions and its figures, then underlined tabs —
   * Overview, Permissions, Storage · 5S, Sensitivity, Quota, Activity.
   */
  type StorageRootTag = Record<string, unknown>;
  type StorageRootTabKey = 'overview' | 'effective-access' | 'storage' | 'sensitivity' | 'quota' | 'activity';
  type StorageRootAlertItem = {
    key: string;
    type?: string;
    title: string;
    subtitle?: string | null;
    tone?: 'warning' | 'error';
  };

  interface Props {
    detailsLoading?: boolean;
    selectedStorageRootId?: number | null;
    selectedRootCodeOrName?: string;
    zoneLabel?: string;
    activeTab?: StorageRootTabKey;
    rootProbeBusy?: boolean;
    aclFreshness?: Record<string, unknown> | null;
    alertItems?: StorageRootAlertItem[];
    endpointLabel?: string;
    endpointAddress?: string;
    pathLabel?: string;
    content?: any;
    sensitivity?: any;
    endpointHref?: string | null;
    guardians?: Array<Record<string, unknown>>;
    rootAvailabilityText?: any;
    rootAvailabilityTone?: 'success' | 'warning' | 'error';
    tags?: StorageRootTag[];
    isAdmin?: boolean;
    isDfs?: boolean;
    selectedRow?: Record<string, any> | null;
    /** Login whose access is explained at once (?explain= from the ⌘K palette) */
    explainLogin?: string | null;
    /** Bumped by the page after an operation on the folder: the permissions are read again */
    refreshKey?: number;
    activityRemainder?: Array<Record<string, unknown>>;
    activityLoading?: boolean;
    tagId?: (tag: StorageRootTag) => number;
    tagLabel?: (tag: StorageRootTag) => string;
    tagColor?: (tag: StorageRootTag) => string | null;
    ownerDisplayName?: (owner: Record<string, unknown>) => string;
    onSelectTab?: (tab: StorageRootTabKey) => void;
    onDeleteRoot?: () => void;
    onRunRootProbe?: () => void;
    /** A measure landed: the overview is read again */
    onReloadDetails?: () => void;
    onNewAccessRequest?: () => void;
    onOpenGovernanceDrawer?: (role?: 'guardian') => void;
    onOpenTagsModal?: () => void;
    onViewAllAlerts?: () => void;
    /** Operation on the folder on the file server (inheritance, deletion, sub-folder), run by the page */
    onFolderAction?: (kind: FolderActionKind, inheritanceBroken: boolean | null) => void;
    /** Measure and sensitivity scan from the band (administrators) */
    onMeasure?: (() => void) | null;
    onScanSensitivity?: (() => void) | null;
  }

  let {
    detailsLoading = false,
    selectedStorageRootId = null,
    selectedRootCodeOrName = '—',
    zoneLabel = '',
    activeTab = 'overview',
    rootProbeBusy = false,
    aclFreshness = null,
    alertItems = [],
    endpointLabel = '—',
    endpointAddress = '—',
    pathLabel = '—',
    content = null,
    sensitivity = null,
    endpointHref = null,
    guardians = [],
    rootAvailabilityText = t('Unknown'),
    rootAvailabilityTone = 'warning',
    tags = [],
    isAdmin = false,
    isDfs = false,
    selectedRow = null,
    explainLogin = null,
    refreshKey = 0,
    activityRemainder = [],
    activityLoading = false,
    tagId = () => 0,
    tagLabel = () => t('Tag'),
    tagColor = () => null,
    ownerDisplayName = () => t('Unknown'),
    onSelectTab = () => {},
    onDeleteRoot = () => {},
    onRunRootProbe = () => {},
    onReloadDetails = () => {},
    onNewAccessRequest = () => {},
    onOpenGovernanceDrawer = () => {},
    onOpenTagsModal = () => {},
    onViewAllAlerts = () => {},
    onFolderAction = () => {},
    onMeasure = null,
    onScanSensitivity = null
  }: Props = $props();

  // Permissions: one computation (ACL read on the file server x AD groups x requests) for the tab and the figures.
  // Loaded again when another root is selected, when an ACL read ends and after an action in the tab.
  let permissions: StorageRootPermissionsData | null = $state(null);
  let permissionsLoading = $state(false);
  let permissionsError: string | null = $state(null);
  let permissionsKey = '';
  let permissionsSeq = 0;

  function syncPermissions(key: string) {
    if (key === permissionsKey) return;
    if (permissions?.storage_root_id !== selectedStorageRootId) permissions = null;
    permissionsKey = key;
    void loadPermissions();
  }

  async function loadPermissions() {
    const rootId = selectedStorageRootId;
    if (!rootId) return;
    const seq = ++permissionsSeq;
    permissionsLoading = true;
    permissionsError = null;
    try {
      const result = await getStorageRootPermissions(fetch, rootId);
      if (seq === permissionsSeq) permissions = result;
    } catch (error: unknown) {
      if (seq === permissionsSeq) permissionsError = presentErrorMessage(toAppError(error));
    } finally {
      if (seq === permissionsSeq) permissionsLoading = false;
    }
  }

  // One status pill: the folder unreachable first, then the state of its ACL
  const ACL_PILL = {
    ok: { label: () => t('Compliant'), tone: 'success' },
    applying: { label: () => t('Being applied'), tone: 'warning' },
    gap: { label: () => t('Gap to review'), tone: 'warning' },
    missing_ace: { label: () => t('ACE missing'), tone: 'danger' },
    never_scanned: { label: () => t('To verify'), tone: 'neutral' }
  } as const;

  // « Who reaches it? » typed in the overview opens the permissions tab on that login
  let explainTyped: string | null = $state(null);
  function explainFromOverview(login: string) {
    explainTyped = login;
    onSelectTab('effective-access');
  }

  let showBlockingLoading = $derived(detailsLoading && selectedRootCodeOrName === '—');
  let endpointDisplay = $derived(endpointAddress && endpointAddress !== '—' ? endpointAddress : endpointLabel);
  let aclScannedAt = $derived(String(aclFreshness?.scanned_at ?? aclFreshness?.discovered_at ?? '').trim());
  $effect.pre(() => {
    if (selectedStorageRootId && !rootProbeBusy) syncPermissions(`${selectedStorageRootId}:${aclScannedAt}:${refreshKey}`);
  });
  let unreachable = $derived(rootAvailabilityTone === 'error');
  let guardianMissing = $derived(alertItems.some((item) => item.type === 'missing_guardian' || /missing_guardian/.test(String(item.key ?? ''))));
  let aclState = $derived(permissions?.status ?? 'never_scanned');
  // « Compliant » only speaks of a folder with nothing left to do: its guardians count too
  let pill = $derived(unreachable
    ? { label: rootAvailabilityText, tone: 'danger' as const }
    : aclState === 'ok' && guardianMissing && $governanceEnabled
      ? { label: t('Guardians missing'), tone: 'warning' as const }
      : { label: ACL_PILL[aclState].label(), tone: ACL_PILL[aclState].tone });
  let inheritanceBroken = $derived(permissions?.inheritance?.known ? permissions.inheritance.broken : null);
  // Badges of the tabs: files flagged by the last sensitivity scan, quota requests waiting
  let flagged = $derived(Number(selectedRow?.password_files ?? 0) + Number(selectedRow?.key_files ?? 0) + Number(selectedRow?.personal_files ?? 0));
  let quotaWaiting = $derived(Number(selectedRow?.quota_pending_requests ?? 0));
  let tabs = $derived([
    { key: 'overview', label: t('Overview') },
    // Who reaches the folder: the exposure, part of the governance
    ...($governanceEnabled ? [{ key: 'effective-access', label: t('Permissions'), count: permissions?.summary.people }] : []),
    // The detail of the content and its sensitivity come with the 5S module (size and files stay in the figures)
    ...($fivesEnabled ? [{ key: 'storage', label: t('Storage · 5S') }, { key: 'sensitivity', label: t('Sensitivity'), count: flagged || undefined }] : []),
    { key: 'quota', label: t('Quota'), count: quotaWaiting || undefined },
    { key: 'activity', label: t('Activity') }
  ] as Array<{ key: StorageRootTabKey; label: string; count?: number }>);
  let current = $derived(tabs.some((tab) => tab.key === activeTab) ? activeTab : 'overview');
  let guardianNames = $derived(guardians.map((owner) => ownerDisplayName(owner)).filter(Boolean));
  $effect.pre(() => {
    if (selectedStorageRootId) explainTyped = null;
  });

  // Arrow keys move between the tabs (ARIA tabs pattern)
  function onTabKey(event: KeyboardEvent) {
    if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return;
    event.preventDefault();
    const index = tabs.findIndex((tab) => tab.key === current);
    const next = tabs[(index + (event.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length];
    onSelectTab(next.key);
    (event.currentTarget as HTMLElement).querySelector<HTMLButtonElement>(`[data-tab="${next.key}"]`)?.focus();
  }
</script>

<div class="sr-detail">
  {#if showBlockingLoading}
    <LoadingState skeleton="page" rows={5}>{t('Loading storage root data…')}</LoadingState>
  {/if}

  <div class="sr-head">
    <StorageRootHeader
      title={selectedRootCodeOrName}
      {zoneLabel}
      {endpointLabel}
      {pathLabel}
      statusLabel={selectedStorageRootId ? pill.label : ''}
      statusTone={pill.tone}
      {rootProbeBusy}
      {selectedStorageRootId}
      {isAdmin}
      {inheritanceBroken}
      {onRunRootProbe}
      {onNewAccessRequest}
      {onDeleteRoot}
      {onMeasure}
      {onScanSensitivity}
      onToggleInheritance={() => onFolderAction('inheritance', inheritanceBroken)}
      onDeleteFolder={() => onFolderAction('delete', inheritanceBroken)}
      onCreateSubfolder={() => onFolderAction('subfolder', inheritanceBroken)}
    />

    <StorageRootTiles
      {permissions}
      row={selectedRow}
      onOpenContent={() => onSelectTab($fivesEnabled ? 'storage' : 'overview')}
      onOpenPermissions={() => onSelectTab('effective-access')}
    />
  </div>

  <StorageRootTodo
    rootId={selectedStorageRootId}
    {alertItems}
    busy={rootProbeBusy}
    onRunProbe={onRunRootProbe}
    onOpenGuardians={() => onOpenGovernanceDrawer('guardian')}
    onOpenPermissions={() => onSelectTab('effective-access')}
    {onViewAllAlerts}
    rootName={selectedRootCodeOrName}
  />

  <div class="v2-tabs" role="tablist" aria-label={t('Storage root sections')} tabindex="-1" onkeydown={onTabKey}>
    {#each tabs as tab (tab.key)}
      <button type="button" role="tab" data-tab={tab.key} class:is-on={current === tab.key} aria-selected={current === tab.key}
        tabindex={current === tab.key ? 0 : -1} onclick={() => onSelectTab(tab.key)}>
        {tab.label}{#if tab.count}<b>{tab.count}</b>{/if}
      </button>
    {/each}
  </div>

  {#if current === 'overview' || current === 'storage' || current === 'sensitivity' || current === 'quota'}
    <!-- One instance per folder: its scans, measures and quota never show on another folder (nor its late answers) -->
    {#key `${selectedStorageRootId}:${current}`}
    {#if current === 'overview' && $governanceEnabled}
      <!-- The state of the folder's ACL first: who reaches it, through which groups, repair and export -->
      <StorageRootPermissions
        mode="acl"
        data={permissions}
        loading={permissionsLoading}
        error={permissionsError}
        rootId={selectedStorageRootId}
        rootName={selectedRootCodeOrName}
        canManage={true}
        {isAdmin}
        onChanged={loadPermissions}
        onToggleInheritance={() => onFolderAction('inheritance', inheritanceBroken)}
      />
    {/if}
    <StorageRootOverview
      section={current}
      {permissions}
      {guardianNames}
      guardiansMissing={guardianMissing}
      activity={activityRemainder}
      {tags}
      {tagId}
      {tagLabel}
      {tagColor}
      {zoneLabel}
      {endpointDisplay}
      {endpointHref}
      {content}
      {sensitivity}
      {isDfs}
      rootId={selectedStorageRootId}
      onMeasured={onReloadDetails}
      {isAdmin}
      onExplain={explainFromOverview}
      onOpenActivity={() => onSelectTab('activity')}
      onOpenGuardians={() => onOpenGovernanceDrawer('guardian')}
      onOpenTags={onOpenTagsModal}
      onToggleInheritance={() => onFolderAction('inheritance', inheritanceBroken)}
      onChanged={loadPermissions}
    />
    {/key}
  {:else if current === 'effective-access'}
    <section class="sr-clean-tab-panel" role="tabpanel">
      <!-- The page is open to admins and to the guardians of the root: both review its requests -->
      <StorageRootPermissions
        data={permissions}
        loading={permissionsLoading}
        error={permissionsError}
        rootId={selectedStorageRootId}
        rootName={selectedRootCodeOrName}
        canManage={true}
        {isAdmin}
        explainLogin={explainTyped ?? explainLogin}
        onChanged={loadPermissions}
        onToggleInheritance={() => onFolderAction('inheritance', inheritanceBroken)}
      />
    </section>
  {:else if current === 'activity'}
    <section class="sr-clean-tab-panel" role="tabpanel">
      {#if activityLoading}
        <LoadingState skeleton="rows" rows={6}>{t('Loading activity...')}</LoadingState>
      {:else}
        <ActivityTimeline items={activityRemainder} emptyLabel={t('No activity found for this storage root.')} />
      {/if}
    </section>
  {/if}
</div>

<style>
  .sr-detail {
    min-width: 0;
    display: grid;
    gap: 20px;
    align-content: start;
  }

  .sr-head { display: grid; gap: 16px; }
</style>
