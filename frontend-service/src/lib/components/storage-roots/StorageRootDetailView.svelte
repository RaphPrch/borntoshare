<script lang="ts">
  import { governanceEnabled } from '$lib/utils/features';
  

  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import { t } from '$lib/i18n';
  import Tabs from '$lib/components/ui/Tabs.svelte';
  import StorageRootHeader from '$lib/components/storage-roots/StorageRootHeader.svelte';
  import StorageRootTiles from '$lib/components/storage-roots/StorageRootTiles.svelte';
  import StorageRootTodo from '$lib/components/storage-roots/StorageRootTodo.svelte';
  import StorageRootOverview from '$lib/components/storage-roots/StorageRootOverview.svelte';
  import StorageRootPermissions from '$lib/components/storage-roots/permissions/StorageRootPermissions.svelte';
  import ActivityTimeline from '$lib/components/activity/ActivityTimeline.svelte';
  import { presentErrorMessage, toAppError } from '$lib/errors';
  import { getStorageRootPermissions, type StorageRootPermissionsData } from '$lib/api/storage-root-permissions';
  import type { FolderActionKind } from '$lib/components/storage-roots/StorageRootFolderActions.svelte';

  type StorageRootTag = Record<string, unknown>;
  type StorageRootTabKey = 'overview' | 'effective-access' | 'activity';
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
    onEditRoot?: () => void;
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
    onEditRoot = () => {},
    onDeleteRoot = () => {},
    onRunRootProbe = () => {},
    onReloadDetails = () => {},
    onNewAccessRequest = () => {},
    onOpenGovernanceDrawer = () => {},
    onOpenTagsModal = () => {},
    onViewAllAlerts = () => {},
    onFolderAction = () => {}
  }: Props = $props();


  // Permissions: one computation (ACL read on the file server x AD groups x requests) for the tab and the KPIs.
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

  const normalizeTabKey = (key: string): StorageRootTabKey => {
    if (key === 'effective-access') return 'effective-access';
    if (key === 'activity') return 'activity';
    return 'overview';
  };
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
  let tabs = $derived([
    { key: 'overview', label: t('Overview'), icon: 'bi-grid' },
    // Who reaches the folder: the exposure, part of the governance
    ...($governanceEnabled ? [{ key: 'effective-access', label: t('Permissions'), icon: 'bi-shield-lock', count: permissions?.summary.people }] : []),
    { key: 'activity', label: t('Activity'), icon: 'bi-clock-history' }
  ]);
  let guardianNames = $derived(guardians.map((owner) => ownerDisplayName(owner)).filter(Boolean));
  $effect.pre(() => {
    if (selectedStorageRootId) explainTyped = null;
  });
</script>

<div class="sr-detail">
  {#if showBlockingLoading}
    <LoadingState skeleton="page" rows={5}>{t('Loading storage root data…')}</LoadingState>
  {/if}

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
    {onEditRoot}
    {onDeleteRoot}
    onToggleInheritance={() => onFolderAction('inheritance', inheritanceBroken)}
    onDeleteFolder={() => onFolderAction('delete', inheritanceBroken)}
    onCreateSubfolder={() => onFolderAction('subfolder', inheritanceBroken)}
  />

  <StorageRootTiles
    {permissions}
    row={selectedRow}
    onOpenContent={() => { onSelectTab('overview'); document.querySelector('.cc')?.scrollIntoView({ behavior: 'smooth', block: 'start' }); }}
    onOpenPermissions={() => onSelectTab('effective-access')}
  />

  <StorageRootTodo
    rootId={selectedStorageRootId}
    {alertItems}
    busy={rootProbeBusy}
    onRunProbe={onRunRootProbe}
    onOpenGuardians={() => onOpenGovernanceDrawer('guardian')}
    onOpenPermissions={() => onSelectTab('effective-access')}
    {onViewAllAlerts}
    onDecided={loadPermissions}
  />

  <Tabs
    {tabs}
    activeKey={activeTab}
    ariaLabel={t('Storage root sections')}
    onChange={(key) => onSelectTab(normalizeTabKey(key))}
  />

  {#if activeTab === 'overview' || (activeTab === 'effective-access' && !$governanceEnabled)}
    <!-- One instance per folder: its scans, measures and quota never show on another folder (nor its late answers) -->
    {#key selectedStorageRootId}
    <StorageRootOverview
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
  {:else if activeTab === 'effective-access'}
    <section class="sr-clean-tab-panel">
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
  {:else if activeTab === 'activity'}
    <section class="sr-clean-tab-panel">
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

</style>
