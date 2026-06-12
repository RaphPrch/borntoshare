import { toAdSourceOptions } from './ad-browse';

declare const process: { exitCode?: number };

function assert(condition: unknown, message: string): void {
  if (!condition) throw new Error(message);
}

function testKeepsOnlySearchableSnapshotSources(): void {
  const rows = toAdSourceOptions([
    {
      id: 6,
      name: 'CORP RAPH',
      type: 'ad',
      is_active: true,
      base_dn: 'DC=CORP,DC=LOCAL',
      last_snapshot_status: 'ACTIVE',
      last_snapshot_users_count: 6,
      last_snapshot_groups_count: 51,
      last_snapshot_objects_count: 57,
      capabilities: { snapshot_enabled: true, import_groups: true }
    },
    {
      id: 5,
      name: 'Legacy LDAP Directory',
      type: 'ad',
      is_active: true,
      base_dn: 'DC=legacy,DC=corp,DC=local',
      last_snapshot_status: null,
      capabilities: { snapshot_enabled: true }
    },
    {
      id: 4,
      name: 'Azure AD',
      type: 'oidc',
      is_active: true
    },
    {
      id: 3,
      name: 'Subsidiary Directory',
      type: 'ad',
      is_active: true,
      last_snapshot_status: 'SUCCEEDED'
    }
  ]);

  assert(rows.length === 2, 'only searchable AD snapshot sources should remain');
  assert(rows.some((row) => row.id === 6), 'CORP RAPH should remain');
  assert(rows.some((row) => row.id === 3), 'SUCCEEDED snapshot source should remain');
  assert(!rows.some((row) => row.id === 5), 'source without active/succeeded snapshot should be hidden');
  assert(rows.find((row) => row.id === 6)?.usersCount === 6, 'users count should be preserved');
  assert(rows.find((row) => row.id === 6)?.groupsCount === 51, 'groups count should be preserved');
}

async function run(): Promise<void> {
  testKeepsOnlySearchableSnapshotSources();
}

run().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
