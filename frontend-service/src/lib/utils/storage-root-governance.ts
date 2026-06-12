import type { StorageRootOwner, StorageRootOwnerRole } from '../api/storage-roots';

export type IdentityImportCandidateRow = {
  is_import_candidate?: boolean | null;
};

export type GovernanceOwnerDraft = {
  guardianIds: number[];
  metadataByIdentityId: Record<number, Partial<StorageRootOwner>>;
};

export type GovernanceBrowserSelection = {
  guardianIds: number[];
  assignedRole?: StorageRootOwnerRole;
  metadataByIdentityId?: Record<number, Partial<StorageRootOwner>>;
  unresolvedPrincipalLabels?: string[];
};

const asPositiveInt = (value: unknown): number | null => {
  const parsed = Number(value ?? 0);
  if (!Number.isFinite(parsed) || parsed <= 0) return null;
  return Math.trunc(parsed);
};

export const normalizeOwnerRole = (value: unknown): StorageRootOwnerRole =>
  'guardian';

export const normalizeAssignedRole = (value: unknown): StorageRootOwnerRole => normalizeOwnerRole(value);

export const normalizeOwnerIds = (input: unknown[]): number[] =>
  Array.from(
    new Set(
      (input ?? [])
        .map((value) => asPositiveInt(value))
        .filter((value): value is number => Number.isFinite(value as number) && Number(value) > 0)
    )
  );

export const sameOwnerIdSet = (left: unknown[], right: unknown[]): boolean => {
  const a = normalizeOwnerIds(left);
  const b = normalizeOwnerIds(right);
  if (a.length !== b.length) return false;
  const rightSet = new Set(b);
  return a.every((id) => rightSet.has(id));
};

export const splitOwnersByRole = (owners: Array<Partial<StorageRootOwner>>): {
  guardians: StorageRootOwner[];
} => {
  const guardians: StorageRootOwner[] = [];

  for (const candidate of owners ?? []) {
    const identityId = asPositiveInt(candidate?.identity_id ?? 0);
    if (!identityId) continue;

    const owner: StorageRootOwner = {
      storage_root_id: Number(candidate?.storage_root_id ?? 0),
      identity_id: identityId,
      role: normalizeOwnerRole(candidate?.role),
      display_name: candidate?.display_name ?? null,
      username: candidate?.username ?? null,
      email: candidate?.email ?? null,
      identity_type: candidate?.identity_type ?? null
    };

    guardians.push(owner);
  }

  return {
    guardians: deduplicateOwners(guardians)
  };
};

export const deduplicateOwners = (owners: StorageRootOwner[]): StorageRootOwner[] => {
  const seen = new Set<string>();
  const out: StorageRootOwner[] = [];
  for (const owner of owners ?? []) {
    const identityId = asPositiveInt(owner?.identity_id ?? 0);
    if (!identityId) continue;
    const role = normalizeOwnerRole(owner?.role);
    const key = `${identityId}:${role}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({
      ...owner,
      identity_id: identityId,
      role
    });
  }
  return out;
};

export const buildGovernanceDraftFromOwners = (
  owners: StorageRootOwner[],
  seedMetadata: Record<number, Partial<StorageRootOwner>> = {}
): GovernanceOwnerDraft => {
  const { guardians } = splitOwnersByRole(owners);
  const metadataByIdentityId: Record<number, Partial<StorageRootOwner>> = {
    ...(seedMetadata ?? {})
  };

  for (const owner of guardians) {
    const identityId = asPositiveInt(owner?.identity_id ?? 0);
    if (!identityId) continue;
    metadataByIdentityId[identityId] = {
      ...(metadataByIdentityId[identityId] ?? {}),
      ...owner,
      identity_id: identityId,
      role: normalizeOwnerRole(owner?.role)
    };
  }

  return {
    guardianIds: normalizeOwnerIds(guardians.map((owner) => owner.identity_id)),
    metadataByIdentityId
  };
};

export const mergeBrowserSelectionIntoDraft = (
  currentDraft: GovernanceOwnerDraft,
  selection: GovernanceBrowserSelection
): GovernanceOwnerDraft => {
  const guardianIds = normalizeOwnerIds(selection.guardianIds ?? []);

  const nextMetadata: Record<number, Partial<StorageRootOwner>> = {
    ...(currentDraft?.metadataByIdentityId ?? {})
  };
  const incomingMetadata = selection.metadataByIdentityId ?? {};

  for (const identityId of guardianIds) {
    nextMetadata[identityId] = {
      ...(nextMetadata[identityId] ?? {}),
      ...(incomingMetadata[identityId] ?? {}),
      identity_id: identityId
    };
  }

  return {
    guardianIds,
    metadataByIdentityId: nextMetadata
  };
};

export const removeOwnerFromDraft = (
  draft: GovernanceOwnerDraft,
  params: { identityId: number; role: StorageRootOwnerRole }
): GovernanceOwnerDraft => {
  const identityId = asPositiveInt(params.identityId);
  if (!identityId) return draft;

  return {
    ...draft,
    guardianIds: normalizeOwnerIds((draft.guardianIds ?? []).filter((id) => Number(id) !== identityId))
  };
};

export const buildOwnersUpdatePayload = (draft: GovernanceOwnerDraft): {
  guardian_ids: number[];
} => ({
  guardian_ids: normalizeOwnerIds(draft.guardianIds ?? [])
});

export const hasGovernanceDraftChanges = (
  initialDraft: GovernanceOwnerDraft,
  currentDraft: GovernanceOwnerDraft
): boolean =>
  !sameOwnerIdSet(initialDraft?.guardianIds ?? [], currentDraft?.guardianIds ?? []);

export const governanceOwnersDraftForRole = (
  role: StorageRootOwnerRole,
  storageRootId: number,
  persistedOwners: StorageRootOwner[],
  draft: GovernanceOwnerDraft
): Array<StorageRootOwner & Record<string, unknown>> => {
  const persistedById = new Map<number, StorageRootOwner>();
  const normalizedRole = normalizeOwnerRole(role);
  for (const owner of persistedOwners ?? []) {
    const identityId = asPositiveInt(owner?.identity_id ?? 0);
    if (!identityId) continue;
    if (normalizeOwnerRole(owner?.role) !== normalizedRole) continue;
    persistedById.set(identityId, owner);
  }

  return normalizeOwnerIds(draft.guardianIds).map((identityId) => ({
    storage_root_id: Number(storageRootId ?? persistedById.get(identityId)?.storage_root_id ?? 0),
    identity_id: identityId,
    role: normalizedRole,
    ...(draft.metadataByIdentityId?.[identityId] ?? {}),
    ...(persistedById.get(identityId) ?? {})
  }));
};

export const normalizeUnresolvedPrincipalLabels = (labels: unknown[]): string[] =>
  Array.from(
    new Set(
      (labels ?? [])
        .map((value) => String(value ?? '').trim())
        .filter(Boolean)
    )
  );

export const shouldResetGovernanceDraftFromOwners = (draftDirty: boolean): boolean => !draftDirty;

export const filterIdentityRowsByImportPolicy = <T extends IdentityImportCandidateRow>(
  rows: T[],
  includeImportCandidates: boolean
): T[] => {
  if (includeImportCandidates) return [...(rows ?? [])];
  return (rows ?? []).filter((row) => !Boolean(row?.is_import_candidate));
};
