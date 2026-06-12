import {
  buildIdentitySourceSummary,
  filterIdentitySourceCards,
  filterIdentitySourcesByQuery,
  mapIdentitySourceToCardVM,
  sortIdentitySourceCards,
  type IdentitySourceRowLike
} from './identity-sources.mapper';
import {
  extractSnapshotMeta,
  toSnapshotStorePatch,
  type IdentitySourceInternalMeta
} from '../identity-sources.helpers';

declare const process: { exitCode?: number };

function assert(condition: unknown, message: string): void {
  if (!condition) throw new Error(message);
}

function makeSource(partial: Partial<IdentitySourceRowLike>): IdentitySourceRowLike {
  return {
    id: Number(partial.id ?? 1),
    type: partial.type ?? 'ad',
    name: partial.name ?? `source-${partial.id ?? 1}`,
    protocol: partial.protocol ?? 'ldaps',
    host: partial.host,
    port: partial.port,
    base_dn: partial.base_dn,
    bind_dn: partial.bind_dn,
    status: partial.status,
    is_active: partial.is_active ?? true,
    used: partial.used,
    last_probe_at: partial.last_probe_at,
    last_snapshot_at: partial.last_snapshot_at,
    last_snapshot_status: partial.last_snapshot_status,
    last_snapshot_version: partial.last_snapshot_version,
    last_snapshot_objects_count: partial.last_snapshot_objects_count,
    last_snapshot_users_count: partial.last_snapshot_users_count,
    last_snapshot_groups_count: partial.last_snapshot_groups_count,
    last_snapshot_memberships_count: partial.last_snapshot_memberships_count,
    capabilities: partial.capabilities
  };
}

function testExtractSnapshotMetaAndPatch(): void {
  const internal: IdentitySourceInternalMeta = {
    id: 77,
    last_snapshot_at: '2026-02-10T12:00:00Z',
    last_snapshot_status: 'ACTIVE',
    last_snapshot_version: 3,
    last_snapshot_objects_count: 42,
    last_snapshot_users_count: 30,
    last_snapshot_groups_count: 12,
    last_snapshot_memberships_count: 88
  };

  const meta = extractSnapshotMeta(internal);
  assert(meta.at === '2026-02-10T12:00:00Z', 'extractSnapshotMeta.at should be extracted');
  assert(meta.status === 'ACTIVE', 'extractSnapshotMeta.status should be extracted');
  assert(meta.version === 3, 'extractSnapshotMeta.version should be extracted');
  assert(meta.objects === 42, 'extractSnapshotMeta.objects should be extracted');
  assert(meta.users === 30, 'extractSnapshotMeta.users should be extracted');
  assert(meta.groups === 12, 'extractSnapshotMeta.groups should be extracted');
  assert(meta.memberships === 88, 'extractSnapshotMeta.memberships should be extracted');

  const patch = toSnapshotStorePatch(meta);
  assert(patch.lastRunAt === meta.at, 'toSnapshotStorePatch.lastRunAt should map from meta.at');
  assert(
    patch.lastSnapshotObjectsCount === meta.objects,
    'toSnapshotStorePatch.lastSnapshotObjectsCount should map from meta.objects'
  );
  assert(
    patch.lastSnapshotMembershipsCount === meta.memberships,
    'toSnapshotStorePatch.lastSnapshotMembershipsCount should map from meta.memberships'
  );
}

function testMapIdentitySourceToCardVm(): void {
  const source = makeSource({
    id: 1,
    name: 'corp-ad',
    type: 'ad',
    host: 'dc1.corp.local',
    port: 636,
    bind_dn: 'CN=svc,DC=corp,DC=local',
    base_dn: 'DC=corp,DC=local',
    status: 'connected',
    is_active: true,
    last_probe_at: '2026-02-09T12:00:00Z',
    capabilities: { snapshot_enabled: true }
  });

  const card = mapIdentitySourceToCardVM(source, {
    probeJobStatus: 'running',
    snapshotJobStatus: 'running',
    snapshotMeta: {
      lastRunAt: '2026-02-10T12:00:00Z',
      lastSnapshotStatus: 'success',
      lastSnapshotVersion: 4,
      lastSnapshotObjectsCount: 100,
      lastSnapshotUsersCount: 70,
      lastSnapshotGroupsCount: 30,
      lastSnapshotMembershipsCount: 220
    }
  });

  assert(card.healthTone === 'info', 'healthTone should be info when probe is running');
  assert(card.healthLabel === 'Probe running', 'healthLabel should indicate probe in progress');
  assert(card.snapshotTone === 'info', 'snapshotTone should be info when snapshot is running');
  assert(card.snapshotLabel === 'Snapshot in progress', 'snapshotLabel should indicate snapshot in progress');
  assert(card.endpointLabel === 'dc1.corp.local:636', 'endpointLabel should include host and port');
  assert(card.usersCount === 70, 'usersCount should prefer snapshot meta');
  assert(card.groupsCount === 30, 'groupsCount should prefer snapshot meta');
  assert(card.membershipsCount === 220, 'membershipsCount should prefer snapshot meta');
  assert(card.lastProbeLabel === 'Probe in progress', 'lastProbeLabel should reflect running state');
}

function testMapIdentitySourceToCardVmSnapshotDisabled(): void {
  const source = makeSource({
    id: 9,
    name: 'no-snapshot',
    type: 'ad',
    capabilities: { snapshot_enabled: false },
    last_snapshot_at: '2026-02-10T12:00:00Z',
    last_snapshot_status: 'success'
  });

  const card = mapIdentitySourceToCardVM(source);
  assert(card.supportsSnapshot === false, 'supportsSnapshot should be disabled when snapshot_enabled is false');
  assert(card.snapshotLabel === 'Not applicable', 'snapshotLabel should be not applicable when snapshot is disabled');
}

function testFilterAndSortAndSummary(): void {
  const sources: IdentitySourceRowLike[] = [
    makeSource({
      id: 1,
      name: 'alpha-ad',
      type: 'ad',
      base_dn: 'DC=alpha,DC=local',
      status: 'healthy',
      is_active: true,
      last_probe_at: '2026-02-01T10:00:00Z',
      last_snapshot_at: '2026-02-01T09:00:00Z',
      last_snapshot_status: 'success',
      capabilities: { snapshot_enabled: true }
    }),
    makeSource({
      id: 2,
      name: 'beta-ad',
      type: 'ad',
      status: 'offline',
      is_active: true,
      last_probe_at: '2026-02-01T11:00:00Z',
      last_snapshot_status: 'failed',
      capabilities: { snapshot_enabled: true }
    }),
    makeSource({
      id: 3,
      name: 'gamma-ad',
      type: 'ad',
      status: 'warning',
      is_active: true,
      last_probe_at: '2026-02-01T12:00:00Z',
      capabilities: { snapshot_enabled: true }
    }),
    makeSource({
      id: 4,
      name: 'delta-ad',
      type: 'ad',
      status: 'connected',
      is_active: false,
      last_probe_at: '2026-02-01T08:00:00Z',
      capabilities: { snapshot_enabled: true }
    })
  ];

  const byQuery = filterIdentitySourcesByQuery(sources, 'alpha');
  assert(byQuery.length === 1 && byQuery[0].id === 1, 'filterIdentitySourcesByQuery should match textual query');

  const cards = sources.map((source) => mapIdentitySourceToCardVM(source));

  const issues = filterIdentitySourceCards(cards, { status: 'issues' });
  const issueIds = new Set(issues.map((card) => card.id));
  assert(issueIds.has(2), 'issues filter should include error tone');
  assert(issueIds.has(3), 'issues filter should include warning tone');
  assert(!issueIds.has(4), 'issues filter should exclude disabled tone');

  const never = filterIdentitySourceCards(cards, { snapshot: 'never' });
  const neverIds = new Set(never.map((card) => card.id));
  assert(neverIds.has(3), 'snapshot=never should include source without snapshot metadata');
  assert(neverIds.has(4), 'snapshot=never should include source without snapshot metadata');
  assert(!neverIds.has(1), 'snapshot=never should exclude synced source');

  const sortedProbe = sortIdentitySourceCards(cards, 'recent-probe');
  assert(sortedProbe[0].id === 3, 'recent-probe should sort by latest probe first');
  assert(sortedProbe[sortedProbe.length - 1].id === 4, 'recent-probe should sort by oldest probe last');

  const summary = buildIdentitySourceSummary(cards);
  assert(summary.total === 4, 'summary.total should count all cards');
  assert(summary.healthy === 1, 'summary.healthy should count success health tone only');
  assert(summary.issues === 2, 'summary.issues should count warning + error tones');
  assert(summary.neverSynced === 2, 'summary.neverSynced should count cards with empty snapshot status/date only');
}

async function run(): Promise<void> {
  testExtractSnapshotMetaAndPatch();
  testMapIdentitySourceToCardVm();
  testMapIdentitySourceToCardVmSnapshotDisabled();
  testFilterAndSortAndSummary();
}

run().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
