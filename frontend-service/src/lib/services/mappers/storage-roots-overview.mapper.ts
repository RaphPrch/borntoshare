export type AccessProfileRow = Record<string, any>;
export type ProjectedAdGroupRow = Record<string, any>;

export function profileAccessLevel(row: AccessProfileRow | null | undefined): 'READ' | 'WRITE' {
  const candidates = [
    row?.access_level,
    row?.access_level_code,
    row?.code,
    row?.permission,
    row?.name,
    row?.label,
  ];
  for (const candidate of candidates) {
    const normalized = String(candidate ?? '').trim().toUpperCase();
    if (normalized === 'READ') return 'READ';
    if (normalized === 'WRITE') return 'WRITE';
  }
  return 'READ';
}

export function profileSourceLabel(row: AccessProfileRow | null | undefined): 'Inherited' | 'Direct' {
  return String(row?.profile_source ?? row?.source ?? '').toLowerCase() === 'inherited'
    ? 'Inherited'
    : 'Direct';
}

export function profilePermissionLabel(level: 'READ' | 'WRITE'): string {
  return level === 'WRITE' ? 'Write' : 'Read';
}

export function profileMembersCount(row: AccessProfileRow | null | undefined): number {
  return Number(row?.members_count ?? row?.members ?? 0);
}

export function projectedGroupProvisioningStatus(row: ProjectedAdGroupRow | null | undefined): string {
  const status = String(row?.profile_status ?? '').trim().toUpperCase();
  if (status === 'SUCCEEDED') return 'Provisioned';
  if (status === 'RUNNING' || status === 'QUEUED' || status === 'RETRYING') return 'Provisioning';
  if (status === 'FAILED') return 'Failed';
  if (status === 'NOT_CREATED') return 'Not created';
  return status || 'Pending';
}

export function computeSummaryKpis(input: {
  accessProfilesRows: AccessProfileRow[];
  readAccessCount: number;
  writeAccessCount: number;
  pendingValidationCount: number;
}) {
  const accessProfiles = Array.isArray(input.accessProfilesRows) ? input.accessProfilesRows : [];
  const profilesApplied = accessProfiles.length;
  const profilesRead = accessProfiles.filter((row) => profileAccessLevel(row) === 'READ').length;
  const profilesWrite = accessProfiles.filter((row) => profileAccessLevel(row) === 'WRITE').length;
  const usersWithAccess = Math.max(0, Number(input.readAccessCount || 0) + Number(input.writeAccessCount || 0));
  const pendingRequests = Math.max(0, Number(input.pendingValidationCount || 0));
  return {
    profilesApplied,
    profilesRead,
    profilesWrite,
    usersWithAccess,
    pendingRequests,
  };
}
