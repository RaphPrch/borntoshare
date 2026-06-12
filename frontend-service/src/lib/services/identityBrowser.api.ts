import type { FetchLike } from '../api/client';
import { apiGet, apiGetData, apiPostData } from '../api/client';
import type {
  IdentityBrowserSource,
  IdentityPreview,
  IdentitySearchResponse,
  IdentityTreeNode
} from '../types/identityBrowser';
import { toAdSourceOptions } from '../utils/ad-browse';
import { normalizePrincipalList } from '../utils/principal-search';
import { getIdentitySourceInternal, listIdentitySources } from '../api/identity-sources';

const asArray = <T>(value: unknown): T[] => (Array.isArray(value) ? (value as T[]) : []);

const MAX_DIRECTORY_BROWSE_LIMIT = 200;
const IDENTITY_SOURCE_INTERNAL_CACHE_TTL_MS = 4000;

type IdentitySourceInternalCacheEntry = {
  value: IdentitySourceInternalPayload | null;
  expiresAt: number;
};

type IdentitySourceInternalPayload = {
  base_dn?: string | null;
  baseDn?: string | null;
  last_snapshot_at?: string | null;
  [key: string]: unknown;
};

type IdentityBrowseApiResponse = {
  count?: number;
  items?: unknown[];
  users?: unknown[];
  groups?: unknown[];
  [key: string]: unknown;
};

type BrowserScope = 'subtree' | 'onelevel' | 'base';
type BrowserPrincipalType = 'all' | 'user' | 'group' | 'ou';

type BrowserRawQuery = {
  sourceId: number;
  q: string;
  dn: string;
  principalType: BrowserPrincipalType;
  scope: BrowserScope;
  limit: number;
  enabledOnly: boolean;
};

const identitySourceInternalCache = new Map<number, IdentitySourceInternalCacheEntry>();
const identitySourceInternalInFlight = new Map<number, Promise<IdentitySourceInternalPayload | null>>();

const clampDirectoryBrowseLimit = (value: unknown, fallback = 50): string => {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return String(fallback);
  const normalized = Math.trunc(parsed);
  if (normalized < 1) return '1';
  return String(Math.min(MAX_DIRECTORY_BROWSE_LIMIT, normalized));
};

const normalizeSourceId = (value: unknown): number | null => {
  const parsed = Number(value ?? 0);
  if (!Number.isFinite(parsed) || parsed <= 0) return null;
  return Math.trunc(parsed);
};

const normalizeBrowserPrincipalType = (value: unknown): BrowserPrincipalType => {
  const principalType = String(value ?? 'all').trim().toLowerCase();
  if (principalType === 'user' || principalType === 'group' || principalType === 'ou') {
    return principalType;
  }
  return 'all';
};

const normalizeBrowserScope = (value: unknown, fallback: BrowserScope): BrowserScope => {
  const scope = String(value ?? '').trim().toLowerCase();
  if (scope === 'subtree' || scope === 'onelevel' || scope === 'base') {
    return scope;
  }
  return fallback;
};

const buildBrowseQueryParams = (params: BrowserRawQuery): Record<string, string | boolean> => ({
  q: String(params.q ?? '').trim(),
  dn: String(params.dn ?? '').trim(),
  principal_type: normalizeBrowserPrincipalType(params.principalType),
  scope: normalizeBrowserScope(params.scope, 'onelevel'),
  limit: clampDirectoryBrowseLimit(params.limit ?? 50, 50),
  enabled_only: toBooleanFlag(params.enabledOnly)
});

const rawBrowseDirectory = async (
  fetchFn: FetchLike,
  params: BrowserRawQuery
): Promise<IdentityBrowseApiResponse> => {
  const query = buildBrowseQueryParams(params);
  return await apiPostData<IdentityBrowseApiResponse>(fetchFn, '/identity/search', {
    identity_source_id: params.sourceId,
    query: String(query.q ?? '').trim(),
    dn: String(query.dn ?? '').trim(),
    base_dn: String(query.dn ?? '').trim(),
    principal_type: String(query.principal_type ?? 'all').trim().toLowerCase(),
    search_scope: String(query.scope ?? 'subtree').trim().toLowerCase(),
    limit: Number(query.limit ?? 50),
    enabled_only: Boolean(query.enabled_only)
  });
};

const normalizeBrowseResponse = (payload: IdentityBrowseApiResponse): IdentitySearchResponse => {
  const items = normalizePrincipalList(payload);
  const count = Number(payload?.count ?? items.length ?? 0) || 0;
  return { items, count };
};

const isSecretResolutionError = (error: unknown): boolean => {
  const message = String((error as any)?.message ?? error ?? '').toLowerCase();
  return message.includes('secret') || message.includes('secret_not_found') || message.includes('secret not found');
};

const normalizeTreeChildrenFromBrowse = (rows: IdentityPreview[], activeRoot: string): IdentityTreeNode[] =>
  (rows ?? [])
    .filter((row) => String(row?.type ?? '').toLowerCase() === 'ou')
    .map((row) => {
      const nodeDn = String(row?.dn ?? '').trim();
      if (!nodeDn || nodeDn.toLowerCase() === activeRoot.toLowerCase()) return null;
      return {
        dn: nodeDn,
        name: String(row?.display_name ?? row?.username ?? nodeDn).trim() || nodeDn,
        type: 'ou',
        has_children: true,
        loaded: false,
        children: []
      } as IdentityTreeNode;
    })
    .filter((row): row is IdentityTreeNode => Boolean(row));

export function invalidateIdentitySourceInternalCache(sourceId?: number | null): void {
  const normalizedId = Number(sourceId ?? 0);
  if (Number.isFinite(normalizedId) && normalizedId > 0) {
    identitySourceInternalCache.delete(normalizedId);
    identitySourceInternalInFlight.delete(normalizedId);
    return;
  }
  identitySourceInternalCache.clear();
  identitySourceInternalInFlight.clear();
}

export async function loadIdentitySourceInternalCached(
  fetchFn: FetchLike,
  sourceId: number,
  options?: { force?: boolean; ttlMs?: number; signal?: AbortSignal }
): Promise<IdentitySourceInternalPayload | null> {
  const normalizedSourceId = Number(sourceId ?? 0);
  if (!Number.isFinite(normalizedSourceId) || normalizedSourceId <= 0) {
    return null;
  }

  const signal = options?.signal;
  if (signal?.aborted) return null;

  const force = options?.force === true;
  const ttlMs = Math.max(0, Math.trunc(Number(options?.ttlMs ?? IDENTITY_SOURCE_INTERNAL_CACHE_TTL_MS) || 0));
  const now = Date.now();

  if (!force) {
    const cached = identitySourceInternalCache.get(normalizedSourceId);
    if (cached && cached.expiresAt > now) {
      return cached.value;
    }

    const inFlight = identitySourceInternalInFlight.get(normalizedSourceId);
    if (inFlight) {
      return await inFlight;
    }
  }

  const promise = (async () => {
    const internalRaw = await getIdentitySourceInternal(fetchFn, normalizedSourceId);
    const internal =
      internalRaw && typeof internalRaw === 'object'
        ? (internalRaw as IdentitySourceInternalPayload)
        : null;
    if (!signal?.aborted) {
      identitySourceInternalCache.set(normalizedSourceId, {
        value: internal,
        expiresAt: Date.now() + ttlMs
      });
    }
    return internal;
  })();

  identitySourceInternalInFlight.set(normalizedSourceId, promise);
  try {
    return await promise;
  } finally {
    identitySourceInternalInFlight.delete(normalizedSourceId);
  }
}

const normalizeDn = (value: unknown): string =>
  String(value ?? '')
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean)
    .join(',');

const firstNonEmpty = (...values: unknown[]): string | null => {
  for (const value of values) {
    const normalized = normalizeDn(value);
    if (normalized) return normalized;
  }
  return null;
};

const toBooleanFlag = (value: unknown): boolean => {
  if (typeof value === 'boolean') return value;
  const normalized = String(value ?? '').trim().toLowerCase();
  return normalized === '1' || normalized === 'true' || normalized === 'yes' || normalized === 'on';
};

const parseRdnName = (rdn: string): string => {
  const raw = String(rdn ?? '').trim();
  if (!raw) return 'OU';
  const idx = raw.indexOf('=');
  if (idx < 0) return raw;
  return raw.slice(idx + 1).trim() || 'OU';
};

const collectImmediateChildOusFromDescendants = (
  descendants: Array<{ dn?: string | null }>,
  activeRoot: string
): IdentityTreeNode[] => {
  const rootNorm = normalizeDn(activeRoot);
  if (!rootNorm) return [];

  const out = new Map<string, { dn: string; name: string; hasChildren: boolean }>();
  const rootNormLower = rootNorm.toLowerCase();

  for (const row of descendants ?? []) {
    const dnNorm = normalizeDn(row?.dn);
    if (!dnNorm) continue;
    const dnLower = dnNorm.toLowerCase();
    if (dnLower === rootNormLower) continue;

    const suffix = `,${rootNorm}`;
    if (!dnLower.endsWith(suffix.toLowerCase())) continue;

    const prefix = dnNorm.slice(0, dnNorm.length - suffix.length).trim();
    if (!prefix) continue;

    const segments = prefix.split(',').map((part) => part.trim()).filter(Boolean);
    if (segments.length === 0) continue;
    const immediateRdn = String(segments[segments.length - 1] ?? '').trim();
    if (!immediateRdn.toLowerCase().startsWith('ou=')) continue;

    const childDn = `${immediateRdn},${rootNorm}`;
    const key = childDn.toLowerCase();
    if (out.has(key)) continue;

    const hasChildren = segments.length > 1;
    out.set(key, {
      dn: childDn,
      name: parseRdnName(immediateRdn),
      hasChildren
    });
  }

  return Array.from(out.values())
    .map((item) => ({
      dn: item.dn,
      name: item.name,
      type: 'ou',
      has_children: item.hasChildren,
      loaded: false,
      children: []
    }))
    .sort((a, b) => String(a.name).localeCompare(String(b.name), 'en'));
};

export type IdentityBrowserResolvedContext = {
  sourceId: number | null;
  rootDn: string | null;
  rootDnResolution: 'storage_endpoint_sub_ou_dn' | 'storage_root_effective_ou' | 'identity_source_base_dn' | 'none';
};

type StorageRootOverviewPayload = {
  effective_provisioning?: {
    identity_source_id?: number | null;
    group_ou?: string | null;
  };
  provisioning_policy?: {
    resolved_identity_source_id?: number | null;
    resolved_group_ou?: string | null;
    endpoint_sub_ou_dn?: string | null;
    effective?: {
      endpoint_sub_ou_dn?: string | null;
      effective_ou_dn?: string | null;
    };
    effective_preview?: {
      effective_ou_dn?: string | null;
    };
  };
};

const resolveContextFromOverview = (
  overview: StorageRootOverviewPayload,
  fallbackSourceId: number | null
): IdentityBrowserResolvedContext => {
  const sourceId =
    normalizeSourceId(
      overview?.effective_provisioning?.identity_source_id ??
        overview?.provisioning_policy?.resolved_identity_source_id ??
        fallbackSourceId ??
        0
    ) ?? null;

  const endpointOu = firstNonEmpty(
    overview?.provisioning_policy?.effective?.endpoint_sub_ou_dn,
    overview?.provisioning_policy?.endpoint_sub_ou_dn
  );
  if (endpointOu) {
    return {
      sourceId,
      rootDn: endpointOu,
      rootDnResolution: 'storage_endpoint_sub_ou_dn'
    };
  }

  const effectiveOu = firstNonEmpty(
    overview?.effective_provisioning?.group_ou,
    overview?.provisioning_policy?.resolved_group_ou,
    overview?.provisioning_policy?.effective?.effective_ou_dn,
    overview?.provisioning_policy?.effective_preview?.effective_ou_dn
  );
  if (effectiveOu) {
    return {
      sourceId,
      rootDn: effectiveOu,
      rootDnResolution: 'storage_root_effective_ou'
    };
  }

  return {
    sourceId,
    rootDn: null,
    rootDnResolution: 'none'
  };
};

export async function resolveIdentityBrowserContext(
  fetchFn: FetchLike,
  params: {
    storageRootId?: number | null;
    preferredSourceId?: number | null;
  }
): Promise<IdentityBrowserResolvedContext> {
  const fallbackSourceId = normalizeSourceId(params.preferredSourceId ?? 0);
  const storageRootId = Number(params.storageRootId ?? 0);
  if (!Number.isFinite(storageRootId) || storageRootId <= 0) {
    return {
      sourceId: fallbackSourceId,
      rootDn: null,
      rootDnResolution: 'none'
    };
  }

  try {
    const overview = await apiGetData<StorageRootOverviewPayload>(fetchFn, `/storage-roots/${storageRootId}/overview`);
    return resolveContextFromOverview(overview, fallbackSourceId);
  } catch {
    return {
      sourceId: fallbackSourceId,
      rootDn: null,
      rootDnResolution: 'none'
    };
  }
}

export async function listIdentityBrowserSources(fetchFn: FetchLike): Promise<IdentityBrowserSource[]> {
  const payload = await listIdentitySources(fetchFn);
  return toAdSourceOptions(payload);
}

export async function loadIdentityTree(
  fetchFn: FetchLike,
  sourceId: number,
  dn?: string | null,
  signal?: AbortSignal,
  options?: {
    rootDnOverride?: string | null;
  }
): Promise<IdentityTreeNode[]> {
  if (signal?.aborted) return [];
  const rootDn = normalizeDn(dn);

  let baseDn = '';
  if (!rootDn) {
    baseDn = normalizeDn(options?.rootDnOverride);
    if (!baseDn) {
      try {
        const internal = await loadIdentitySourceInternalCached(fetchFn, sourceId, { signal });
        baseDn = normalizeDn(internal?.base_dn ?? internal?.baseDn);
      } catch {
        baseDn = '';
      }
    }
  }

  const activeRoot = rootDn || baseDn;
  if (!activeRoot) return [];

  let childNodes: IdentityTreeNode[] = [];
  try {
    const childrenPayload = await rawBrowseDirectory(fetchFn, {
      sourceId,
      q: '',
      dn: activeRoot,
      principalType: 'ou',
      scope: 'onelevel',
      limit: MAX_DIRECTORY_BROWSE_LIMIT,
      enabledOnly: false
    });
    if (signal?.aborted) return [];
    childNodes = normalizeTreeChildrenFromBrowse(normalizeBrowseResponse(childrenPayload).items as IdentityPreview[], activeRoot);
  } catch (error) {
    if (!isSecretResolutionError(error)) {
      throw error;
    }
    childNodes = [];
  }

  // Fallback when OU projection is missing/stale: infer immediate child OUs from descendant principals.
  if (childNodes.length === 0) {
    try {
      const descendants = await searchIdentityDirectory(fetchFn, {
        sourceId,
        q: '',
        dn: activeRoot,
        scope: 'subtree',
        principalType: 'all',
        enabledOnly: false,
        limit: MAX_DIRECTORY_BROWSE_LIMIT
      });
      if (!signal?.aborted) {
        childNodes = collectImmediateChildOusFromDescendants(descendants.items as Array<{ dn?: string | null }>, activeRoot);
      }
    } catch {
      // keep empty childNodes
    }
  }

  if (!rootDn) {
    return [
      {
        dn: activeRoot,
        name: activeRoot,
        type: 'ou',
        has_children: true,
        loaded: true,
        children: childNodes
      }
    ];
  }

  return childNodes
    .map((row) => {
      const nodeDn = String(row?.dn ?? '').trim();
      if (!nodeDn) return null;
      return {
        dn: nodeDn,
        name: String(row?.name ?? row?.dn ?? nodeDn).trim() || nodeDn,
        type: String(row?.type ?? 'ou').trim().toLowerCase(),
        has_children: true,
        loaded: false,
        children: []
      } as IdentityTreeNode;
    })
    .filter((row): row is IdentityTreeNode => Boolean(row));
}

export async function searchIdentityDirectory(
  fetchFn: FetchLike,
  params: {
    sourceId: number;
    q?: string;
    dn?: string | null;
    scope?: 'subtree' | 'onelevel' | 'base';
    principalType?: 'all' | 'user' | 'group' | 'ou';
    enabledOnly?: boolean;
    limit?: number;
  },
  signal?: AbortSignal
): Promise<IdentitySearchResponse> {
  if (signal?.aborted) return { items: [], count: 0 };

  const fallbackScope = String(params.q ?? '').trim() ? 'subtree' : 'onelevel';
  const resolvedScope = normalizeBrowserScope(params.scope, fallbackScope);

  const payload = await rawBrowseDirectory(fetchFn, {
    sourceId: params.sourceId,
    q: String(params.q ?? '').trim(),
    dn: String(params.dn ?? '').trim(),
    principalType: normalizeBrowserPrincipalType(params.principalType),
    scope: resolvedScope,
    limit: Number(params.limit ?? 50),
    enabledOnly: toBooleanFlag(params.enabledOnly)
  });

  if (signal?.aborted) return { items: [], count: 0 };
  return normalizeBrowseResponse(payload);
}

export async function loadOuContent(
  fetchFn: FetchLike,
  params: {
    sourceId: number;
    dn: string;
    query?: string;
    scope?: 'subtree' | 'onelevel' | 'base';
    limit?: number;
    enabledUsersOnly?: boolean;
  },
  signal?: AbortSignal
): Promise<{ users: IdentityPreview[]; groups: IdentityPreview[]; items: IdentityPreview[]; count: number }> {
  if (signal?.aborted) {
    return { users: [], groups: [], items: [], count: 0 };
  }

  const query = String(params.query ?? '').trim();
  const requestedScope = params.scope ?? 'onelevel';
  const limit = params.limit ?? 200;

  const runScopedSearch = async (scope: 'subtree' | 'onelevel' | 'base') => {
    const [usersResponse, groupsResponse] = await Promise.all([
      searchIdentityDirectory(
        fetchFn,
        {
          sourceId: params.sourceId,
          q: query,
          dn: params.dn,
          scope,
          principalType: 'user',
          enabledOnly: params.enabledUsersOnly ?? true,
          limit
        },
        signal
      ),
      searchIdentityDirectory(
        fetchFn,
        {
          sourceId: params.sourceId,
          q: query,
          dn: params.dn,
          scope,
          principalType: 'group',
          enabledOnly: false,
          limit
        },
        signal
      )
    ]);
    return { usersResponse, groupsResponse };
  };

  const normalizeOuContentRows = (
    usersResponse: IdentitySearchResponse,
    groupsResponse: IdentitySearchResponse
  ) => {
    const users = (usersResponse.items ?? [])
      .filter((row) => String(row?.type ?? '').toLowerCase() === 'user')
      .filter((row) => (params.enabledUsersOnly ?? true ? row?.enabled !== false : true)) as IdentityPreview[];
    const groups = (groupsResponse.items ?? []).filter(
      (row) => String(row?.type ?? '').toLowerCase() === 'group'
    ) as IdentityPreview[];
    return { users, groups };
  };

  let { usersResponse, groupsResponse } = await runScopedSearch(requestedScope);
  let normalized = normalizeOuContentRows(usersResponse, groupsResponse);

  // Fallback UX: when one-level OU browsing returns nothing and query is empty,
  // broaden once to subtree so snapshot-backed users nested under containers
  // (ex: CN=Users, OU children) remain visible in the browser list.
  if (
    !query &&
    requestedScope === 'onelevel' &&
    normalized.users.length + normalized.groups.length === 0
  ) {
    ({ usersResponse, groupsResponse } = await runScopedSearch('subtree'));
    normalized = normalizeOuContentRows(usersResponse, groupsResponse);
  }

  const users = normalized.users;
  const groups = normalized.groups;
  return {
    users,
    groups,
    items: [...users, ...groups],
    count: users.length + groups.length
  };
}

export async function loadIdentityPreview(
  fetchFn: FetchLike,
  params: {
    sourceId: number;
    dn: string;
    principalType?: 'all' | 'user' | 'group' | 'ou';
  },
  signal?: AbortSignal
): Promise<IdentityPreview | null> {
  if (signal?.aborted) return null;
  try {
    const response = await searchIdentityDirectory(
      fetchFn,
      {
        sourceId: params.sourceId,
        q: '',
        dn: params.dn,
        scope: 'base',
        principalType: params.principalType ?? 'all',
        enabledOnly: false,
        limit: 10
      },
      signal
    );
    if (signal?.aborted) return null;
    const exactDn = normalizeDn(params.dn).toLowerCase();
    const exact = response.items.find((item) => normalizeDn(item?.dn).toLowerCase() === exactDn) ?? null;
    return (exact ?? response.items[0] ?? null) as IdentityPreview | null;
  } catch {
    return null;
  }
}

export async function loadIdentitySourceLastSync(
  fetchFn: FetchLike,
  sourceId: number,
  options?: { signal?: AbortSignal; force?: boolean }
): Promise<string | null> {
  try {
    const internal = await loadIdentitySourceInternalCached(fetchFn, sourceId, {
      signal: options?.signal,
      force: options?.force === true
    });
    if (options?.signal?.aborted) return null;
    return String(internal?.last_snapshot_at ?? '').trim() || null;
  } catch {
    return null;
  }
}
