<script lang="ts">
  import { t } from '$lib/i18n';
  import EntityAlertStrip from '$lib/components/entity/EntityAlertStrip.svelte';
  import Tabs from '$lib/components/ui/Tabs.svelte';
  import StorageRootHeader from '$lib/components/storage-roots/StorageRootHeader.svelte';
  import StorageRootStatLine from '$lib/components/storage-roots/StorageRootStatLine.svelte';
  import StorageRootTodo from '$lib/components/storage-roots/StorageRootTodo.svelte';
  import StorageRootOverview from '$lib/components/storage-roots/StorageRootOverview.svelte';
  import StorageRootLoadingState from '$lib/components/storage-roots/StorageRootLoadingState.svelte';
  import StorageRootPermissions from '$lib/components/storage-roots/permissions/StorageRootPermissions.svelte';
  import ActivityTabPanel from '$lib/components/activity/ActivityTabPanel.svelte';
  import { presentErrorMessage, toAppError } from '$lib/errors';
  import { getStorageRootPermissions, type StorageRootPermissionsData } from '$lib/api/storage-root-permissions';
  import type { FolderActionKind } from '$lib/components/storage-roots/StorageRootFolderActions.svelte';

  type StorageRootTag = Record<string, unknown>;
  type StorageRootTabKey = 'overview' | 'effective-access' | 'activity';
  type StorageRootAlertItem = {
    key: string;
    title: string;
    subtitle?: string | null;
    tone?: 'warning' | 'error';
  };
  type ProbeExecutionState = {
    status?: string;
    message?: string | null;
    jobId?: string | null;
    durationMs?: number | null;
    checks?: Array<Record<string, unknown>>;
  };

  export let detailsLoading = false;
  export let selectedStorageRootId: number | null = null;
  export let selectedRootCodeOrName = '—';
  export let zoneLabel = '';
  export let activeTab: StorageRootTabKey = 'overview';

  export let rootProbeBusy = false;
  export let probeState: ProbeExecutionState | null = null;
  export let aclFreshness: Record<string, unknown> | null = null;

  export let alertItems: StorageRootAlertItem[] = [];

  export let endpointLabel = '—';
  export let endpointAddress = '—';
  export let pathLabel = '—';
  export let contentSizeLabel = '—';
  export let endpointHref: string | null = null;

  export let guardians: Array<Record<string, unknown>> = [];

  export let rootAvailabilityText = t('Unknown');
  export let rootAvailabilityTone: 'success' | 'warning' | 'error' = 'warning';

  export let tags: StorageRootTag[] = [];
  export let isAdmin = false;
  /** Login whose access is explained at once (?explain= from the ⌘K palette) */
  export let explainLogin: string | null = null;
  /** Bumped by the page after an operation on the folder: the permissions are read again */
  export let refreshKey = 0;
  export let activityRemainder: Array<Record<string, unknown>> = [];
  export let activityLoading = false;
  export let tagId: (tag: StorageRootTag) => number = () => 0;
  export let tagLabel: (tag: StorageRootTag) => string = () => t('Tag');
  export let tagColor: (tag: StorageRootTag) => string | null = () => null;
  export let ownerDisplayName: (owner: Record<string, unknown>) => string = () => t('Unknown');

  export let onSelectTab: (tab: StorageRootTabKey) => void = () => {};
  export let onEditRoot: () => void = () => {};
  export let onDeleteRoot: () => void = () => {};
  export let onRunRootProbe: () => void = () => {};
  export let onNewAccessRequest: () => void = () => {};
  export let onOpenGovernanceDrawer: (role?: 'guardian') => void = () => {};
  export let onOpenTagsModal: () => void = () => {};
  export let onViewAllAlerts: () => void = () => {};
  /** Operation on the folder on the file server (inheritance, deletion, sub-folder), run by the page */
  export let onFolderAction: (kind: FolderActionKind, inheritanceBroken: boolean | null) => void = () => {};

  $: showBlockingLoading = detailsLoading && selectedRootCodeOrName === '—';
  // Pending requests are decided in the « To review » line, a missing guardian in the inspector
  $: stripItems = alertItems.filter((item) => !/missing_guardian|pending_access_validation/.test(String(item.key ?? '')));
  $: endpointDisplay = endpointAddress && endpointAddress !== '—' ? endpointAddress : endpointLabel;
  $: aclScannedAt = String(aclFreshness?.scanned_at ?? aclFreshness?.discovered_at ?? '').trim();

  // Permissions: one computation (ACL read on the file server x AD groups x requests) for the tab and the KPIs.
  // Loaded again when another root is selected, when an ACL read ends and after an action in the tab.
  let permissions: StorageRootPermissionsData | null = null;
  let permissionsLoading = false;
  let permissionsError: string | null = null;
  let permissionsKey = '';
  let permissionsSeq = 0;
  $: if (selectedStorageRootId && !rootProbeBusy) syncPermissions(`${selectedStorageRootId}:${aclScannedAt}:${refreshKey}`);

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
    gap: { label: () => t('Gap to review'), tone: 'warning' },
    missing_ace: { label: () => t('ACE missing'), tone: 'danger' },
    never_scanned: { label: () => t('ACL never read'), tone: 'neutral' }
  } as const;
  $: unreachable = rootAvailabilityTone === 'error';
  $: pill = unreachable
    ? { label: rootAvailabilityText, tone: 'danger' as const }
    : { label: ACL_PILL[permissions?.status ?? 'never_scanned'].label(), tone: ACL_PILL[permissions?.status ?? 'never_scanned'].tone };
  $: inheritanceBroken = permissions?.inheritance?.known ? permissions.inheritance.broken : null;

  $: tabs = [
    { key: 'overview', label: t('Overview'), icon: 'bi-grid' },
    { key: 'effective-access', label: t('Permissions'), icon: 'bi-shield-lock', count: permissions?.summary.people },
    { key: 'activity', label: t('Activity'), icon: 'bi-clock-history' }
  ];
  $: guardianNames = guardians.map((owner) => ownerDisplayName(owner)).filter(Boolean);
  $: openAlerts = stripItems.length;

  const normalizeTabKey = (key: string): StorageRootTabKey => {
    if (key === 'effective-access') return 'effective-access';
    if (key === 'activity') return 'activity';
    return 'overview';
  };
</script>

<div class="sr-detail">
  {#if showBlockingLoading}
    <StorageRootLoadingState label={t('Loading storage root data…')} />
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

  <StorageRootStatLine
    {permissions}
    {openAlerts}
    lastProbeText={rootAvailabilityText}
    alertsHref={`/observability?tab=alerts&q=${encodeURIComponent(selectedRootCodeOrName)}`}
    onOpenPermissions={() => onSelectTab('effective-access')}
  />

  <StorageRootTodo rootId={selectedStorageRootId} onDecided={loadPermissions} />

  <EntityAlertStrip items={stripItems} onViewAll={onViewAllAlerts} ariaLabel={t('Storage root alerts')} />

  <Tabs
    {tabs}
    activeKey={activeTab}
    ariaLabel={t('Storage root sections')}
    onChange={(key) => onSelectTab(normalizeTabKey(key))}
  />

  {#if activeTab === 'overview'}
    <StorageRootOverview
      {permissions}
      {guardianNames}
      {tags}
      {tagId}
      {tagLabel}
      {tagColor}
      {zoneLabel}
      {endpointDisplay}
      {endpointHref}
      {contentSizeLabel}
      {isAdmin}
      onOpenPermissions={() => onSelectTab('effective-access')}
      onOpenGuardians={() => onOpenGovernanceDrawer('guardian')}
      onOpenTags={onOpenTagsModal}
      onToggleInheritance={() => onFolderAction('inheritance', inheritanceBroken)}
      onChanged={loadPermissions}
    />
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
        {explainLogin}
        onChanged={loadPermissions}
        onToggleInheritance={() => onFolderAction('inheritance', inheritanceBroken)}
      />
    </section>
  {:else if activeTab === 'activity'}
    <section class="sr-clean-tab-panel">
      {#if activityLoading}
        <StorageRootLoadingState label={t('Loading activity...')} />
      {:else}
        <ActivityTabPanel
          items={activityRemainder}
          emptyLabel={t('No activity found for this storage root.')}
        />
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
