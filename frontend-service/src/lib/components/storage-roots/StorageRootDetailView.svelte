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
  import KpiCard from '$lib/components/ui/KpiCard.svelte';
  import { initials } from '$lib/utils/format';
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
  export let tagLabel: (tag: StorageRootTag) => string = () => t('Tag');
  export let tagColor: (tag: StorageRootTag) => string | null = () => null;
  export let ownerDisplayName: (owner: Record<string, unknown>) => string = () => t('Unknown');

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
        : t('No ACL scan yet');

  $: tabs = [
    { key: 'overview', label: t('Overview'), icon: 'bi-grid' },
    { key: 'effective-access', label: t('Effective access'), icon: 'bi-people', count: effectiveAccessUsers.length },
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
    aclLabel={aclState === 'stale' ? t('ACL stale') : aclScannedAt ? t('ACL fresh') : ''}
    aclTone={aclState === 'stale' ? 'warning' : 'info'}
    {rootProbeBusy}
    {selectedStorageRootId}
    {onRunRootProbe}
    {onNewAccessRequest}
    {onEditRoot}
    {onDeleteRoot}
  />

  <EntityAlertStrip items={alertItems} onViewAll={onViewAllAlerts} ariaLabel={t('Storage root alerts')} />

  <section class="b2s-kpi-grid sr-detail__kpis" aria-label={t('Storage root summary')}>
    <KpiCard
      label={t('Effective access')}
      value={effectiveUsersCount}
      hint={t('{configuredGroupsCount} Groups', { configuredGroupsCount })}
      icon="bi-people"
      tone="info"
    />
    <KpiCard
      label={t('Guardians')}
      value={guardians.length}
      hint={guardianNames.slice(0, 2).join(', ') || t('No guardian yet')}
      icon="bi-shield-check"
      tone={guardians.length > 0 ? 'purple' : 'warning'}
    />
    <KpiCard
      label={t('Last probe')}
      value={lastProbeText}
      hint={aclFreshnessLabel}
      icon="bi-activity"
      tone={rootAvailabilityText === t('Unreachable') ? 'danger' : aclState === 'stale' ? 'warning' : 'success'}
    />
    <KpiCard
      label={t('Open alerts')}
      value={openAlerts}
      hint={openAlerts > 0 ? t('Review them in the alert list') : t('Nothing to review')}
      icon={openAlerts > 0 ? 'bi-exclamation-triangle' : 'bi-check2-circle'}
      tone={openAlerts > 0 ? 'warning' : 'success'}
    />
  </section>

  <Tabs
    {tabs}
    activeKey={activeTab}
    ariaLabel={t('Storage root sections')}
    onChange={(key) => onSelectTab(normalizeTabKey(key))}
  />

  {#if activeTab === 'overview'}
    <section class="b2s-detail-columns">
      <div>
        <article class="b2s-panel">
          <div class="b2s-panel__head">
            <h2>{t('Access profiles')}</h2>
            <button type="button" class="b2s-panel__link" on:click={() => onOpenGovernanceDrawer('guardian')}>
              {t('Manage guardians')}
            </button>
          </div>
          <StorageRootAccessModel rows={accessModelRows} {onOpenEffectiveAccess} />
        </article>

        <RecentActivityCard
          title={t('Recent activity')}
          items={recentActivity}
          max={5}
          emptyText={t('Activity related to this storage root will appear here.')}
          onViewAll={onViewAllActivity}
        />
      </div>

      <aside>
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
              <dt>{t('Endpoint')}</dt><dd>{endpointDisplay}</dd>
              <dt>{t('Path')}</dt><dd class="sr-detail__mono">{pathLabel}</dd>
              <dt>{t('Reachability')}</dt><dd>{rootAvailabilityText}</dd>
              <dt>{t('Content')}</dt><dd>{contentSizeLabel === '—' ? t('Not measured') : contentSizeLabel}</dd>
            </dl>
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
</div>

<style>
  .sr-detail {
    min-width: 0;
    display: grid;
    gap: 20px;
    align-content: start;
  }

  .sr-detail__kpis {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }

  @media (max-width: 1280px) {
    .sr-detail__kpis {
      grid-template-columns: repeat(2, minmax(0, 1fr));
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

  .sr-detail__mono {
    font-family: var(--b2s-font-mono);
    font-size: var(--b2s-fs-xs);
  }
</style>
