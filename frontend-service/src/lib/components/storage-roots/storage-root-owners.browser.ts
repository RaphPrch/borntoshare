export type OwnerAssignedRole = 'guardian';

export type OwnerBrowserPrincipal = {
  id?: string | number;
  type?: string | null;
  identity_id?: number | null;
  external_id?: string | null;
  dn?: string | null;
  username?: string | null;
  display_name?: string | null;
  email?: string | null;
  upn?: string | null;
};

export type IdentityOverviewRow = {
  id?: number | string;
  identity_id?: number | string;
  type?: string | null;
  external_id?: string | null;
  dn?: string | null;
  username?: string | null;
  upn?: string | null;
  email?: string | null;
  display_name?: string | null;
};

export type IdentityOverviewPayload = {
  items?: IdentityOverviewRow[];
  users?: IdentityOverviewRow[];
  groups?: IdentityOverviewRow[];
};

export type IdentityImportBatchResult = {
  items?: Array<{
    index?: number;
    identity_id?: number;
    identity?: { identity_id?: number; id?: number };
    data?: { identity_id?: number; identity?: { identity_id?: number; id?: number } };
  }>;
  results?: Array<Record<string, unknown>>;
  errors?: Array<{ index?: number }>;
  failures?: Array<{ index?: number }>;
};

export type OwnerPrincipalSelection = {
  item: OwnerBrowserPrincipal;
  selectionIndex: number;
};

export type OwnersSelectionNormalizationResult = {
  principalSelections: OwnerPrincipalSelection[];
  selectedPrincipalItems: OwnerBrowserPrincipal[];
  ignoredUnsupportedCount: number;
};

export type OwnersOverviewResolution = {
  resolvedMatches: Array<{ principalIndex: number; identityId: number }>;
  unresolved: string[];
  metadataByIdentityId: Record<number, Record<string, unknown>>;
};

export type MergeOwnersSelectionInput = {
  initialGuardianIds: number[];
  assignedRole: OwnerAssignedRole;
  resolvedIdentityIds: number[];
};

export type MergeOwnersSelectionResult = {
  guardianIds: number[];
  addedCount: number;
  resolvedCount: number;
  alreadyAssignedCount: number;
};

export type OwnersBrowserConfirmPayload = {
  storageRootId: number;
  guardianIds: number[];
  assignedRole: OwnerAssignedRole;
  metadataByIdentityId: Record<number, Record<string, unknown>>;
  unresolvedPrincipalLabels: string[];
};

export type OwnersBrowserSelectionEvent = {
  storageRootId: number;
  guardianIds: number[];
  assignedRole?: OwnerAssignedRole;
  metadataByIdentityId?: Record<number, Record<string, unknown>>;
  unresolvedPrincipalLabels?: string[];
};

export type ApplyOwnersSelectionToDraftParams = {
  currentDraft: {
    guardianIds: number[];
    metadataByIdentityId?: Record<number, Record<string, unknown>>;
  };
  eventDetail: OwnersBrowserSelectionEvent;
  selectedStorageRootId: number | null;
};

export type ApplyOwnersSelectionToDraftResult = {
  rootId: number | null;
  hasValidRootId: boolean;
  guardianIds: number[];
  metadataByIdentityId: Record<number, Record<string, unknown>>;
  assignedRole: OwnerAssignedRole;
  unresolvedPrincipalLabels: string[];
};

const toPositiveInt = (value: unknown): number | null => {
  const parsed = Number(value ?? 0);
  if (!Number.isFinite(parsed) || parsed <= 0) return null;
  return Math.trunc(parsed);
};

const normalizeToken = (value: unknown): string => String(value ?? '').trim().toLowerCase();

const normalizeIdentityIds = (values: unknown[]): number[] =>
  Array.from(
    new Set(
      (values ?? [])
        .map((value) => toPositiveInt(value))
        .filter((value): value is number => Number.isFinite(value as number) && Number(value) > 0)
    )
  );

const normalizeLabels = (labels: unknown[]): string[] =>
  Array.from(
    new Set(
      (labels ?? [])
        .map((value) => String(value ?? '').trim())
        .filter(Boolean)
    )
  );

const principalLookupTokens = (item: OwnerBrowserPrincipal): string[] =>
  Array.from(
    new Set(
      [
        normalizeToken(item?.external_id),
        normalizeToken(item?.dn),
        normalizeToken(item?.id)
      ].filter(Boolean)
    )
  );

export const principalIdentityId = (item: OwnerBrowserPrincipal): number | null => {
  // IMPORTANT: AD browse rows use `id` as principal external identifier (dn/external_id),
  // not as internal SQL identity id.
  return toPositiveInt(item.identity_id ?? 0);
};

export const principalPreviewLabel = (item: OwnerBrowserPrincipal): string =>
  String(item?.username ?? item?.upn ?? item?.email ?? item?.display_name ?? item?.external_id ?? 'unknown');

export const normalizeOwnerBrowserSelection = (selectedItems: OwnerBrowserPrincipal[]): OwnersSelectionNormalizationResult => {
  let ignoredUnsupportedCount = 0;
  const principalSelections = (selectedItems ?? [])
    .map((item, selectionIndex) => ({ item, selectionIndex }))
    .filter(({ item }) => {
      const itemType = String(item?.type ?? 'user').trim().toLowerCase();
      const isSupported = itemType === 'user' || itemType === 'group';
      if (!isSupported) ignoredUnsupportedCount += 1;
      return isSupported;
    });

  return {
    principalSelections,
    selectedPrincipalItems: principalSelections.map(({ item }) => item),
    ignoredUnsupportedCount
  };
};

export const resolveOwnersSelectionMetadata = (
  principals: OwnerBrowserPrincipal[],
  overview: IdentityOverviewPayload | null | undefined
): OwnersOverviewResolution => {
  if (!Array.isArray(principals) || principals.length === 0) {
    return { resolvedMatches: [], unresolved: [], metadataByIdentityId: {} };
  }

  if (!overview) {
    return {
      resolvedMatches: [],
      unresolved: normalizeLabels(principals.map((item) => principalPreviewLabel(item))),
      metadataByIdentityId: {}
    };
  }

  const allItems = Array.isArray(overview?.items)
    ? (overview.items as Array<Record<string, unknown>>)
    : [
        ...((overview?.users ?? []) as Array<Record<string, unknown>>),
        ...((overview?.groups ?? []) as Array<Record<string, unknown>>)
      ];

  const tokenToIdentityId = new Map<string, number>();
  const metadataByIdentityId: Record<number, Record<string, unknown>> = {};
  for (const entry of allItems) {
    const type = String(entry?.type ?? 'user').trim().toLowerCase();
    if (type !== 'user' && type !== 'group') continue;

    const identityId = toPositiveInt(entry?.id ?? entry?.identity_id ?? 0);
    if (!identityId) continue;

    metadataByIdentityId[identityId] = {
      identity_id: identityId,
      display_name: String(entry?.display_name ?? entry?.username ?? entry?.email ?? `Identity #${identityId}`).trim(),
      username: String(entry?.username ?? '').trim() || null,
      upn: String(entry?.upn ?? '').trim() || null,
      email: String(entry?.email ?? '').trim() || null,
      identity_type: type
    };

    const tokens = [
      normalizeToken(entry?.id),
      normalizeToken(entry?.identity_id),
      normalizeToken(entry?.external_id),
      normalizeToken(entry?.dn),
      normalizeToken(entry?.username),
      normalizeToken(entry?.upn),
      normalizeToken(entry?.email)
    ].filter(Boolean);

    for (const token of tokens) {
      if (!tokenToIdentityId.has(token)) {
        tokenToIdentityId.set(token, identityId);
      }
    }
  }

  const resolvedMatches: Array<{ principalIndex: number; identityId: number }> = [];
  const unresolved: string[] = [];

  principals.forEach((principal, principalIndex) => {
    const resolvedId = principalLookupTokens(principal)
      .map((token) => tokenToIdentityId.get(token) ?? null)
      .find((id): id is number => Number.isFinite(id as number) && Number(id) > 0);

    if (resolvedId) {
      resolvedMatches.push({ principalIndex, identityId: resolvedId });
    } else {
      unresolved.push(principalPreviewLabel(principal));
    }
  });

  return {
    resolvedMatches,
    unresolved: normalizeLabels(unresolved),
    metadataByIdentityId
  };
};

export const extractImportedIdentityId = (row: Record<string, unknown>): number | null => {
  const parsed = toPositiveInt(
    row?.identity_id ??
      row?.id ??
      (row?.identity as Record<string, unknown> | null | undefined)?.identity_id ??
      (row?.identity as Record<string, unknown> | null | undefined)?.id ??
      (row?.data as Record<string, unknown> | null | undefined)?.identity_id ??
      (row?.data as Record<string, unknown> | null | undefined)?.id ??
      ((row?.data as Record<string, unknown> | null | undefined)?.identity as Record<string, unknown> | null | undefined)
        ?.identity_id ??
      ((row?.data as Record<string, unknown> | null | undefined)?.identity as Record<string, unknown> | null | undefined)?.id ??
      0
  );

  return parsed;
};

export const mergeOwnersSelectionWithDraft = (input: MergeOwnersSelectionInput): MergeOwnersSelectionResult => {
  const initialGuardianIds = normalizeIdentityIds(input.initialGuardianIds ?? []);
  const resolvedIdentityIds = normalizeIdentityIds(input.resolvedIdentityIds ?? []);

  const guardianSet = new Set(initialGuardianIds);
  const targetSet = guardianSet;
  const initialTargetSet = new Set(initialGuardianIds);

  for (const identityId of resolvedIdentityIds) {
    targetSet.add(identityId);
  }

  const addedCount = [...targetSet].filter((id) => !initialTargetSet.has(id)).length;
  const resolvedCount = resolvedIdentityIds.length;
  const alreadyAssignedCount = Math.max(0, resolvedCount - addedCount);

  return {
    guardianIds: [...guardianSet],
    addedCount,
    resolvedCount,
    alreadyAssignedCount
  };
};

export const buildOwnersBrowserConfirmPayload = (input: {
  storageRootId: number;
  assignedRole: OwnerAssignedRole;
  guardianIds: number[];
  metadataByIdentityId: Record<number, Record<string, unknown>>;
  unresolvedLabels: unknown[];
}): OwnersBrowserConfirmPayload => ({
  storageRootId: Number(input.storageRootId ?? 0),
  guardianIds: normalizeIdentityIds(input.guardianIds ?? []),
  assignedRole: 'guardian',
  metadataByIdentityId: input.metadataByIdentityId ?? {},
  unresolvedPrincipalLabels: normalizeLabels(input.unresolvedLabels ?? [])
});

export const applyOwnersBrowserSelectionToDraft = (
  params: ApplyOwnersSelectionToDraftParams
): ApplyOwnersSelectionToDraftResult => {
  const rootId = toPositiveInt(params.eventDetail?.storageRootId ?? params.selectedStorageRootId ?? 0);
  const normalizedAssignedRole: OwnerAssignedRole = 'guardian';

  const currentGuardianIds = normalizeIdentityIds(params.currentDraft?.guardianIds ?? []);

  const nextGuardianIds = normalizeIdentityIds(params.eventDetail?.guardianIds ?? currentGuardianIds);

  const currentMetadata = (params.currentDraft?.metadataByIdentityId ?? {}) as Record<number, Record<string, unknown>>;
  const incomingMeta = (params.eventDetail?.metadataByIdentityId ?? {}) as Record<number, Record<string, unknown>>;

  const mergedMetadata: Record<number, Record<string, unknown>> = {
    ...currentMetadata
  };

  for (const identityId of nextGuardianIds) {
    mergedMetadata[identityId] = {
      ...(mergedMetadata[identityId] ?? {}),
      ...(incomingMeta[identityId] ?? {}),
      identity_id: identityId
    };
  }

  return {
    rootId,
    hasValidRootId: Boolean(rootId),
    guardianIds: nextGuardianIds,
    metadataByIdentityId: mergedMetadata,
    assignedRole: normalizedAssignedRole,
    unresolvedPrincipalLabels: normalizeLabels(params.eventDetail?.unresolvedPrincipalLabels ?? [])
  };
};
