import {
  buildStorageRootAccessModelRows,
  formatDateTimeLabel,
  ownersInlineSummary,
  storageRootPendingCount,
  storageRootToneFromAvailability,
  storageRootEndpointLabel
} from './storage-root-detail.mapper';

function assert(condition: unknown, message: string): void {
  if (!condition) throw new Error(message);
}

function testStorageRootTone(): void {
  assert(storageRootToneFromAvailability('reachable') === 'healthy', 'reachable should be healthy');
  assert(storageRootToneFromAvailability('checking') === 'warning', 'checking should be warning');
  assert(storageRootToneFromAvailability('unreachable') === 'error', 'unreachable should be error');
}

function testPendingCountPrefersSelectedOverview(): void {
  const count = storageRootPendingCount(
    { storage_root_id: 10, pending_validation_count: 1 },
    10,
    { storage_root_id: 10, pending_validation_count: 4 } as any
  );
  assert(count === 4, 'selected row should prefer overview pending count');
}

function testAccessModelRows(): void {
  const rows = buildStorageRootAccessModelRows({
    storage_root_id: 1,
    owners: [],
    tags: [],
    recent_activity: [],
    access_profiles: [{ access_level: 'READ', members_count: 4 }],
    projected_ad_groups: [{ access_level: 'READ', is_created: true }],
    effective_access: [
      {
        access_level: 'read',
        principal_type: 'ad_group',
        is_acl_group: true,
        members: [
          { identity_id: 1, username: 'alice' },
          { identity_id: 2, username: 'bob' },
          { identity_id: 1, username: 'alice.dup' }
        ]
      },
      { identity_id: 3, username: 'carol', access_level: 'write' }
    ],
    effective_access_counts: { read_users: 0, write_users: 0 },
    pending_validation_count: 0
  });

  assert(rows[0].users === 2, 'READ row should count unique effective users from group members');
  assert(rows[1].users === 1, 'WRITE row should count direct effective users');
  assert(rows[0].adGroupTone === 'success', 'created READ group should be success');
  assert(rows[1].adGroupTone === 'warning', 'missing WRITE group should be warning');
  assert(rows[1].adGroup === 'No group linked', 'missing WRITE group should not display Access Not Created');
}

function testOwnerSummary(): void {
  assert(ownersInlineSummary([], 'No guardian assigned') === '0 · No guardian assigned', 'empty owner summary mismatch');
  assert(
    ownersInlineSummary([{ display_name: 'Alice' }, { username: 'bob' }, { email: 'carol@example.test' }], 'empty') ===
      '3 · Alice, bob +1',
    'owner summary should show first two names and remaining count'
  );
}

function testDateFormattingIsStableForMissingValues(): void {
  assert(formatDateTimeLabel(null) === '—', 'missing date should render dash');
}

function testEndpointLabelResolution(): void {
  // Test avec objet imbriqué (style Detail Model)
  const labelNested = storageRootEndpointLabel({ id: 1 } as any, { id: 1, storage_endpoint: { name: 'NAS-PROD' } });
  assert(labelNested === 'NAS-PROD', 'should resolve nested storage_endpoint.name');

  // Test avec objet plat (style Row)
  const labelFlat = storageRootEndpointLabel({ storage_endpoint_name: 'NAS-BACKUP' } as any, null);
  assert(labelFlat === 'NAS-BACKUP', 'should resolve row storage_endpoint_name');

  // Test de priorité : la donnée endpoint fraîche prime quand elle est fournie.
  const row = { id: 10, storage_endpoint_name: 'Stale-Row-Data' };
  const detailMatch = { id: 10, storage_endpoint: { name: 'Fresh-Detail-Data' } };

  assert(storageRootEndpointLabel(row as any, detailMatch) === 'Fresh-Detail-Data', 'endpoint detail wins');

  // Fallback
  assert(storageRootEndpointLabel(null, null) === '—', 'should fallback to dash');
}

testStorageRootTone();
testPendingCountPrefersSelectedOverview();
testAccessModelRows();
testOwnerSummary();
testDateFormattingIsStableForMissingValues();
testEndpointLabelResolution();
