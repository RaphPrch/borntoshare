<script lang="ts">
  import { t } from '$lib/i18n';
  import EntityAlertStrip from '$lib/components/entity/EntityAlertStrip.svelte';
  import Tabs from '$lib/components/ui/Tabs.svelte';
  import StorageRootHeader from '$lib/components/storage-roots/StorageRootHeader.svelte';
  import StorageRootLoadingState from '$lib/components/storage-roots/StorageRootLoadingState.svelte';
  import StorageRootPermissions from '$lib/components/storage-roots/permissions/StorageRootPermissions.svelte';
  import ActivityTabPanel from '$lib/components/activity/ActivityTabPanel.svelte';
  import TagPill from '$lib/components/tags/TagPill.svelte';
  import KpiCard from '$lib/components/ui/KpiCard.svelte';
  import { initials, timeAgo } from '$lib/utils/format';
  import { getStorageRootPermissions, type StorageRootPermissionsData } from '$lib/api/storage-root-permissions';
  import { presentErrorMessage, toAppError } from '$lib/errors';

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
  export let contentUpdatedLabel = '—';

  export let guardians: Array<Record<string, unknown>> = [];

  export let rootAvailabilityText = t('Unknown');
  export let rootAvailabilityTone: 'success' | 'warning' | 'error' = 'warning';
  export let showStatusBadge = false;

  export let tags: StorageRootTag[] = [];
  export let isAdmin = false;
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

  $: statusTone = rootAvailabilityTone;
  $: showBlockingLoading = detailsLoading && selectedRootCodeOrName === '—';
  $: stripItems = alertItems.filter((item) => !String(item.key ?? '').includes('missing_guardian'));
  $: endpointDisplay = endpointAddress && endpointAddress !== '—' ? endpointAddress : endpointLabel;
  $: aclState = String(aclFreshness?.state ?? '').trim().toLowerCase();
  $: aclScannedAt = String(aclFreshness?.scanned_at ?? aclFreshness?.discovered_at ?? '').trim();

  // Permissions: one computation (ACL read on the file server x AD groups x requests) for the tab and the KPIs.
  // Loaded again when another root is selected, when an ACL read ends and after an action in the tab.
  let permissions: StorageRootPermissionsData | null = null;
  let permissionsLoading = false;
  let permissionsError: string | null = null;
  let permissionsKey = '';
  let permissionsSeq = 0;
  $: if (selectedStorageRootId && !rootProbeBusy) syncPermissions(`${selectedStorageRootId}:${aclScannedAt}`);

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

  const ACL_KPI = {
    ok: { value: () => t('Compliant'), icon: 'bi-shield-check', tone: 'success' },
    gap: { value: () => t('Gap to review'), icon: 'bi-shield-exclamation', tone: 'warning' },
    missing_ace: { value: () => t('ACE missing'), icon: 'bi-shield-x', tone: 'danger' },
    never_scanned: { value: () => t('Never read'), icon: 'bi-shield', tone: 'neutral' }
  } as const;
  $: aclKpi = ACL_KPI[permissions?.status ?? 'never_scanned'];
  $: aclKpiHint = permissions?.acl_scanned_at
    ? t('Read {ago} · {count} entries', { ago: timeAgo(permissions.acl_scanned_at), count: permissions.acl_entries })
    : t('Read the ACL from the Permissions tab');

  $: tabs = [
    { key: 'overview', label: t('Overview'), icon: 'bi-grid' },
    { key: 'effective-access', label: t('Permissions'), icon: 'bi-shield-lock', count: permissions?.summary.people },
    { key: 'activity', label: t('Activity'), icon: 'bi-clock-history' }
  ];
  $: guardianNames = guardians.map((owner) => ownerDisplayName(owner)).filter(Boolean);
  $: openAlerts = alertItems.length;

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
    statusLabel={rootAvailabilityText}
    statusTone={statusTone}
    {showStatusBadge}
    {pathLabel}
    endpointLabel={endpointLabel}
    aclLabel={aclState === 'stale' ? t('ACL stale') : ''}
    aclTone={aclState === 'stale' ? 'warning' : 'info'}
    {rootProbeBusy}
    {selectedStorageRootId}
    {onRunRootProbe}
    {onNewAccessRequest}
    {onEditRoot}
    {onDeleteRoot}
  />

  <!-- « No guardian » is told by the Guardians card, with its action -->
  <EntityAlertStrip items={stripItems} onViewAll={onViewAllAlerts} ariaLabel={t('Storage root alerts')} />

  <section class="b2s-kpi-grid sr-detail__kpis" aria-label={t('Storage root summary')}>
    <KpiCard
      label={t('People with access')}
      value={permissions ? permissions.summary.people : '—'}
      hint={permissions ? t('{read} read · {write} modify', { read: permissions.summary.read, write: permissions.summary.write }) : ''}
      icon="bi-people"
      tone="info"
      href={`?selected=${selectedStorageRootId ?? ''}`}
      on:click={(event) => {
        event.preventDefault();
        onSelectTab('effective-access');
      }}
    />
    <KpiCard
      label={t('State of the ACL')}
      value={aclKpi.value()}
      hint={aclKpiHint}
      icon={aclKpi.icon}
      tone={aclKpi.tone}
    />
    <KpiCard
      label={t('Open alerts')}
      value={openAlerts}
      hint={openAlerts > 0 ? t('Open in Observability') : t('Nothing to review')}
      icon={openAlerts > 0 ? 'bi-exclamation-triangle' : 'bi-check2-circle'}
      tone={openAlerts > 0 ? 'warning' : 'success'}
      href={`/observability?tab=alerts&q=${encodeURIComponent(selectedRootCodeOrName)}`}
    />
  </section>

  <Tabs
    {tabs}
    activeKey={activeTab}
    ariaLabel={t('Storage root sections')}
    onChange={(key) => onSelectTab(normalizeTabKey(key))}
  />

  {#if activeTab === 'overview'}
    <section class="sr-detail__overview">
        <article class="b2s-panel">
          <div class="b2s-panel__head">
            <h2>{t('Guardians')}</h2>
            <button type="button" class="b2s-panel__link" on:click={() => onOpenGovernanceDrawer('guardian')}>{t('Manage')}</button>
          </div>
          <div class="b2s-panel__body">
            {#if guardianNames.length > 0}
              <ul class="sr-detail__people">
                {#each guardianNames as name}
                  <li><span class="sr-detail__avatar">{initials(name)}</span>{name}</li>
                {/each}
              </ul>
            {:else}
              <p class="sr-detail__empty">{t('No guardian assigned. Access requests cannot be approved yet.')}</p>
              <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" on:click={() => onOpenGovernanceDrawer('guardian')}>
                <i class="bi bi-person-plus" aria-hidden="true"></i>{t('Add a guardian')}
              </button>
            {/if}
          </div>
        </article>

        <article class="b2s-panel">
          <div class="b2s-panel__head">
            <h2>{t('Tags')}</h2>
            <button type="button" class="b2s-panel__link" on:click={onOpenTagsModal}>{t('Manage')}</button>
          </div>
          <div class="b2s-panel__body">
            {#if tags.length > 0}
              <div class="sr-detail__tags">
                {#each tags as tag (tagId(tag))}
                  <TagPill label={tagLabel(tag)} color={tagColor(tag)} small={true} />
                {/each}
              </div>
            {:else}
              <p class="sr-detail__empty">{t('No tags attached')}</p>
            {/if}
          </div>
        </article>

        <article class="b2s-panel">
          <div class="b2s-panel__head"><h2>{t('Details')}</h2></div>
          <div class="b2s-panel__body">
            <dl class="b2s-kv">
              <dt>{t('File server')}</dt><dd>{endpointDisplay}</dd>
              <dt>{t('Content')}</dt><dd>{contentSizeLabel === '—' ? t('Not measured') : contentSizeLabel}</dd>
            </dl>
          </div>
        </article>
    </section>
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
        rescanBusy={rootProbeBusy}
        onRescan={selectedStorageRootId ? onRunRootProbe : null}
        onChanged={loadPermissions}
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

  .sr-detail__kpis {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  @media (max-width: 1280px) {
    .sr-detail__kpis {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }

  .sr-detail__overview {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 20px;
    align-items: start;
  }

  @media (max-width: 1100px) {
    .sr-detail__overview {
      grid-template-columns: 1fr;
    }
  }

  .sr-detail__people {
    display: grid;
    gap: 10px;
    margin: 0;
    padding: 0;
    list-style: none;
    font-size: var(--b2s-fs-sm);
  }

  .sr-detail__people li {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .sr-detail__avatar {
    width: 30px;
    height: 30px;
    flex: 0 0 auto;
    display: grid;
    place-items: center;
    border-radius: var(--b2s-radius-pill);
    background: #e0e7ff;
    color: #3730a3;
    font-size: 11px;
    font-weight: 700;
  }

  .sr-detail__tags {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .sr-detail__empty {
    margin: 0;
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-sm);
  }
</style>
