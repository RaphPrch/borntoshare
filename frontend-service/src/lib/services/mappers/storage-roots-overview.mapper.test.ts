import {
  computeSummaryKpis,
  profileAccessLevel,
  profileMembersCount,
  profilePermissionLabel,
  profileSourceLabel,
  projectedGroupProvisioningStatus,
} from './storage-roots-overview.mapper';

declare const process: { exitCode?: number };

function assert(condition: unknown, message: string): void {
  if (!condition) throw new Error(message);
}

function testProfileHelpers(): void {
  assert(profileAccessLevel({ access_level_code: 'read' }) === 'READ', 'access level READ should be normalized');
  assert(profileAccessLevel({ permission: 'WRITE' }) === 'WRITE', 'access level WRITE should be normalized');
  assert(profileSourceLabel({ profile_source: 'inherited' }) === 'Inherited', 'inherited source should be detected');
  assert(profileSourceLabel({ source: 'LOCAL' }) === 'Direct', 'local source should be direct');
  assert(profilePermissionLabel('READ') === 'Read', 'READ permission label should be Read');
  assert(profilePermissionLabel('WRITE') === 'Write', 'WRITE permission label should be Write');
  assert(profileMembersCount({ members_count: 7 }) === 7, 'members_count should be mapped');
  assert(profileMembersCount({ members: 3 }) === 3, 'members fallback should be mapped');
}

function testProjectedGroupStatus(): void {
  assert(projectedGroupProvisioningStatus({ profile_status: 'SUCCEEDED' }) === 'Provisioned', 'SUCCEEDED should map');
  assert(projectedGroupProvisioningStatus({ profile_status: 'RUNNING' }) === 'Provisioning', 'RUNNING should map');
  assert(projectedGroupProvisioningStatus({ profile_status: 'FAILED' }) === 'Failed', 'FAILED should map');
  assert(projectedGroupProvisioningStatus({ profile_status: 'NOT_CREATED' }) === 'Not created', 'NOT_CREATED should map');
}

function testSummaryKpis(): void {
  const kpis = computeSummaryKpis({
    accessProfilesRows: [
      { access_level_code: 'READ' },
      { access_level_code: 'WRITE' },
      { access_level_code: 'READ' },
    ],
    readAccessCount: 12,
    writeAccessCount: 5,
    pendingValidationCount: 4,
  });

  assert(kpis.profilesApplied === 3, 'profilesApplied should count all profiles');
  assert(kpis.profilesRead === 2, 'profilesRead should count READ profiles');
  assert(kpis.profilesWrite === 1, 'profilesWrite should count WRITE profiles');
  assert(kpis.usersWithAccess === 17, 'usersWithAccess should sum read+write users');
  assert(kpis.pendingRequests === 4, 'pendingRequests should map pending count');
}

async function run(): Promise<void> {
  testProfileHelpers();
  testProjectedGroupStatus();
  testSummaryKpis();
}

run().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
