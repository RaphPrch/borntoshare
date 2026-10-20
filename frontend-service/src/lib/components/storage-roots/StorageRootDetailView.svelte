<script lang="ts">
  import { t } from '$lib/i18n';
  import StorageRootAccessModel from '$lib/components/storage-roots/StorageRootAccessModel.svelte';
  import EntityAlertStrip from '$lib/components/entity/EntityAlertStrip.svelte';
  import Tabs from '$lib/components/ui/Tabs.svelte';
  import StorageRootHeader from '$lib/components/storage-roots/StorageRootHeader.svelte';
  import StorageRootLoadingState from '$lib/components/storage-roots/StorageRootLoadingState.svelte';
  import StorageRootEffectiveAccessTable from '$lib/components/storage-roots/StorageRootEffectiveAccessTable.svelte';
  import ActivityTabPanel from '$lib/components/activity/ActivityTabPanel.svelte';
  import RecentActivityCard from '$lib/components/activity/RecentActivityCard.svelte';
  import TagPill from '$lib/components/tags/TagPill.svelte';
  import type {
    StorageRootEffectiveAccessUser,
    StorageRootProjectedAdGroup
  } from '$lib/types/storage-roots';

  type AccessModelRow = {
    level: 'read' | 'write';
    code: string;
    label: string;
    icon: string;
    tone: 'read' | 'write';
    users: number;
    adGroup: string;
    adGroupTone: 'success' | 'pending' | 'warning' | 'neutral';
  };

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
  export let lastProbeDurationLabel = '—';

  export let accessModelRows: AccessModelRow[] = [];
  export let projectedGroups: StorageRootProjectedAdGroup[] = [];
  export let guardians: Array<Record<string, unknown>> = [];

  export let rootAvailabilityText = t('Unknown');
  export let rootAvailabilityTone: 'success' | 'warning' | 'error' = 'warning';
  export let showStatusBadge = false;
  export let lastProbeText = t('Never run');

  export let tags: StorageRootTag[] = [];
  export let effectiveAccessUsers: StorageRootEffectiveAccessUser[] = [];
  export let recentActivity: Array<Record<string, unknown>> = [];
  export let activityRemainder: Array<Record<string, unknown>> = [];
  export let activityLoading = false;
  export let tagId: (tag: StorageRootTag) => number = () => 0;
  export let tagLabel: (tag: StorageRootTag) => string = () => 'Tag';
  export let tagColor: (tag: StorageRootTag) => string | null = () => null;
  export let ownerDisplayName: (owner: Record<string, unknown>) => string = () => 'Unknown';

  export let onSelectTab: (tab: StorageRootTabKey) => void = () => {};
  export let onEditRoot: () => void = () => {};
  export let onDeleteRoot: () => void = () => {};
  export let onRunRootProbe: () => void = () => {};
  export let onNewAccessRequest: () => void = () => {};
  export let onOpenEffectiveAccess: (level: 'read' | 'write') => void = () => {};
  export let onOpenGovernanceDrawer: (role?: 'guardian') => void = () => {};
  export let onOpenTagsModal: () => void = () => {};
  export let onViewAllActivity: () => void = () => {};
  export let onViewAllAlerts: () => void = () => {};

  $: statusTone = rootAvailabilityTone;
  $: showBlockingLoading = detailsLoading && selectedRootCodeOrName === '—';
  $: effectiveUsersCount = accessModelRows.reduce((total, row) => total + Number(row?.users ?? 0), 0);
  $: configuredGroupsCount = accessModelRows.filter((row) => row.adGroupTone === 'success').length;
  $: endpointDisplay = endpointAddress && endpointAddress !== '—' ? endpointAddress : endpointLabel;
  $: aclPermissionsCount = Number(aclFreshness?.permissions_count ?? 0);
  $: aclState = String(aclFreshness?.state ?? '').trim().toLowerCase();
  $: aclScannedAt = String(aclFreshness?.scanned_at ?? aclFreshness?.discovered_at ?? '').trim();
  $: aclSnapshotId = String(aclFreshness?.active_snapshot_id ?? '').trim();
  $: aclFreshnessLabel =
    aclState === 'stale'
      ? t('ACL stale · snapshot {value}', { value: (aclSnapshotId || 'newer') })
      : aclScannedAt
        ? t('{aclPermissionsCount} ACL entries · {value}', { aclPermissionsCount, value: (aclState || 'fresh') })
        : 'No ACL scan yet';

  const tabs: Array<{ key: StorageRootTabKey; label: string; icon: string }> = [
    { key: 'overview', label: t('Overview'), icon: 'bi-grid' },
    { key: 'effective-access', label: t('Effective Access'), icon: 'bi-people' },
    { key: 'activity', label: t('Activity'), icon: 'bi-activity' }
  ];

  const normalizeTabKey = (key: string): StorageRootTabKey => {
    if (key === 'effective-access') return 'effective-access';
    if (key === 'activity') return 'activity';
    return 'overview';
  };
</script>

<main class="sr-clean-main">
  {#if showBlockingLoading}
    <StorageRootLoadingState label={t('Loading storage root data…')} />
  {/if}

  <StorageRootHeader
    title={selectedRootCodeOrName}
    statusLabel={rootAvailabilityText}
    statusTone={statusTone}
    {showStatusBadge}
    {pathLabel}
    {rootProbeBusy}
    {selectedStorageRootId}
    {onRunRootProbe}
    {onNewAccessRequest}
    {onEditRoot}
    {onDeleteRoot}
  />

  <EntityAlertStrip items={alertItems} onViewAll={onViewAllAlerts} ariaLabel={t('Storage root alerts')} />

  <section class="sr-overview-kpis" aria-label={t('Storage root summary')}>
    <article class="sr-overview-kpi">
      <span class="sr-overview-kpi__icon is-access"><i class="bi bi-people" aria-hidden="true"></i></span>
      <div>
        <small>{t('Effective access')}</small>
        <strong>{effectiveUsersCount}</strong>
        <span>{t('{configuredGroupsCount} Groups', { configuredGroupsCount })}</span>
      </div>
    </article>

    <article class="sr-overview-kpi">
      <span class="sr-overview-kpi__icon is-endpoint"><i class="bi bi-hdd-network" aria-hidden="true"></i></span>
      <div>
        <small>{t('Endpoint')}</small>
        <strong>{endpointDisplay}</strong>
        <span>{endpointLabel}</span>
      </div>
    </article>

    <article class="sr-overview-kpi">
      <span class="sr-overview-kpi__icon is-probe"><i class="bi bi-calendar3" aria-hidden="true"></i></span>
      <div>
        <small>{t('Last probe')}</small>
        <strong>{lastProbeText}</strong>
        <span>{aclFreshnessLabel}</span>
      </div>
      {#if rootAvailabilityText === t('Unreachable')}
        <em class="sr-overview-kpi__badge is-error">{t('Failed')}</em>
      {:else if aclState === 'stale'}
        <em class="sr-overview-kpi__badge is-warning">{t('ACL stale')}</em>
      {:else if aclScannedAt}
        <em class="sr-overview-kpi__badge is-success">{t('ACL scanned')}</em>
      {/if}
    </article>

    <article class="sr-overview-kpi">
      <span class="sr-overview-kpi__icon is-content"><i class="bi bi-folder2-open" aria-hidden="true"></i></span>
      <div>
        <small>{t('Content')}</small>
        <strong>{contentSizeLabel}</strong>
        <span>{t('Updated: {contentUpdatedLabel}', { contentUpdatedLabel })}</span>
      </div>
    </article>
  </section>

  <Tabs
    {tabs}
    activeKey={activeTab}
    ariaLabel={t('Storage root sections')}
    onChange={(key) => onSelectTab(normalizeTabKey(key))}
  />

  {#if activeTab === 'overview'}
    <section class="sr-clean-overview">
      <div class="sr-clean-overview__main">
        <article class="sr-clean-card">
          <div class="sr-clean-card__head">
            <h2>{t('Governed access')}</h2>
          </div>
          <StorageRootAccessModel
            rows={accessModelRows}
            {onOpenEffectiveAccess}
          />
        </article>

        <RecentActivityCard
          title={t('Recent activity')}
          items={recentActivity}
          max={5}
          emptyText={t('Activity related to this storage root will appear here.')}
          onViewAll={onViewAllActivity}
        />
      </div>

      <aside class="sr-overview-side">
        <article class="sr-overview-side-card">
          <span class="sr-overview-side-card__icon is-governance"><i class="bi bi-person-gear" aria-hidden="true"></i></span>
          <div>
            <h2>{t('Governance')}</h2>
            <dl>
              <div><dt>{t('Guardians')}</dt><dd>{guardians.length}</dd></div>
            </dl>
            <button type="button" on:click={() => onOpenGovernanceDrawer('guardian')}>
              {t('View governance')} <i class="bi bi-chevron-right" aria-hidden="true"></i>
            </button>
          </div>
        </article>

        <article class="sr-overview-side-card">
          <span class="sr-overview-side-card__icon is-tags"><i class="bi bi-tag" aria-hidden="true"></i></span>
          <div>
            <h2>{t('Tags')}</h2>
            {#if tags.length > 0}
              <div class="sr-overview-tags">
                {#each tags as tag (tagId(tag))}
                  <TagPill label={tagLabel(tag)} color={tagColor(tag)} small={true} />
                {/each}
              </div>
            {:else}
              <p>{t('No tags attached')}</p>
            {/if}
            <button type="button" on:click={onOpenTagsModal}>
              {t('Manage tags')} <i class="bi bi-chevron-right" aria-hidden="true"></i>
            </button>
          </div>
        </article>

        <article class="sr-overview-side-card">
          <span class="sr-overview-side-card__icon is-health"><i class="bi bi-heart-pulse" aria-hidden="true"></i></span>
          <div>
            <h2>{t('Reachability')}</h2>
            <dl>
              <div><dt>{t('Status')}</dt><dd class={`is-${statusTone}`}>{rootAvailabilityText}</dd></div>
            </dl>
            <button type="button" on:click={onViewAllAlerts}>
              {t('View alerts')} <i class="bi bi-chevron-right" aria-hidden="true"></i>
            </button>
          </div>
        </article>
      </aside>
    </section>
  {:else if activeTab === 'effective-access'}
    <section class="sr-clean-tab-panel">
      <StorageRootEffectiveAccessTable
        users={effectiveAccessUsers}
        {projectedGroups}
        {aclFreshness}
        onRescanAcl={selectedStorageRootId ? onRunRootProbe : null}
        rescanBusy={rootProbeBusy}
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
</main>
