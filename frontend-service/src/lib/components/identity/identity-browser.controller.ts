import type { FetchLike } from '../../api/client';
import {
  listIdentityBrowserSources,
  loadIdentityPreview,
  loadIdentityTree,
  loadOuContent,
  resolveIdentityBrowserContext,
  searchIdentityDirectory
} from '../../services/identityBrowser.api';
import type { IdentityBrowserSource, IdentityPreview, IdentityTreeNode } from '../../types/identityBrowser';
import type { PrincipalSearchItem } from '../../utils/principal-search';
import { filterIdentityRowsByImportPolicy } from '../../utils/storage-root-governance';

type BrowserPrincipalType = 'all' | 'user' | 'group' | 'ou';

export type BrowserBootstrapParams = {
  identitySources: IdentityBrowserSource[];
  initialSourceId: number | null;
  sourceId: number | null;
  storageRootId: number | null;
};

export type BrowserBootstrapResult = {
  sources: IdentityBrowserSource[];
  selectedSourceId: number | null;
  resolvedRootDn: string | null;
};

export type BrowserSearchParams = {
  selectedSourceId: number;
  query: string;
  activeDn: string | null;
  resolvedRootDn: string | null;
  principalTypeFilter: BrowserPrincipalType;
  searchLimit: number;
  includeImportCandidates: boolean;
};

const principalTypeFilterPredicate = (item: PrincipalSearchItem, filter: BrowserPrincipalType): boolean => {
  const type = String(item?.type ?? '').toLowerCase();
  if (filter === 'all') return type === 'user' || type === 'group';
  return type === filter;
};

const normalizedSourceId = (value: unknown): number | null => {
  const parsed = Number(value ?? 0);
  if (!Number.isFinite(parsed) || parsed <= 0) return null;
  return Math.trunc(parsed);
};

export async function bootstrapIdentityBrowser(
  fetchFn: FetchLike,
  params: BrowserBootstrapParams
): Promise<BrowserBootstrapResult> {
  const sources =
    Array.isArray(params.identitySources) && params.identitySources.length > 0
      ? params.identitySources
      : await listIdentityBrowserSources(fetchFn);

  const availableSourceIds = new Set(
    (sources ?? [])
      .map((src) => Number(src?.id ?? 0))
      .filter((id) => Number.isFinite(id) && id > 0)
  );

  const preferredSourceCandidate = Number(params.initialSourceId ?? params.sourceId ?? 0);
  const preferredSourceId =
    Number.isFinite(preferredSourceCandidate) && availableSourceIds.has(preferredSourceCandidate)
      ? preferredSourceCandidate
      : null;

  const context = await resolveIdentityBrowserContext(fetchFn, {
    storageRootId: normalizedSourceId(params.storageRootId ?? 0),
    preferredSourceId
  });

  const contextSourceCandidate = Number(context.sourceId ?? 0);
  const contextSourceId =
    Number.isFinite(contextSourceCandidate) && availableSourceIds.has(contextSourceCandidate)
      ? contextSourceCandidate
      : null;

  const fallbackSourceId = preferredSourceId ?? (Number(sources[0]?.id ?? 0) || null);
  const selectedSourceId = contextSourceId ?? fallbackSourceId;
  const resolvedRootDn = String(context.rootDn ?? '').trim() || null;

  return {
    sources,
    selectedSourceId,
    resolvedRootDn
  };
}

export async function loadBrowserRootTree(
  fetchFn: FetchLike,
  params: {
    sourceId: number;
    resolvedRootDn: string | null;
    signal?: AbortSignal;
  }
): Promise<{ nodes: IdentityTreeNode[]; firstDn: string | null }> {
  const nodes = await loadIdentityTree(fetchFn, params.sourceId, null, params.signal, {
    rootDnOverride: params.resolvedRootDn ?? undefined
  });
  return {
    nodes,
    firstDn: nodes[0]?.dn ?? null
  };
}

export async function loadBrowserSubtree(
  fetchFn: FetchLike,
  params: {
    sourceId: number;
    dn: string;
    resolvedRootDn: string | null;
    signal?: AbortSignal;
  }
): Promise<IdentityTreeNode[]> {
  return await loadIdentityTree(fetchFn, params.sourceId, params.dn, params.signal, {
    rootDnOverride: params.resolvedRootDn ?? undefined
  });
}

export async function searchBrowserDirectory(
  fetchFn: FetchLike,
  params: BrowserSearchParams,
  signal?: AbortSignal
): Promise<{ rows: PrincipalSearchItem[]; total: number }> {
  const q = String(params.query ?? '').trim();
  const activeDn = String(params.activeDn ?? '').trim();
  const limit = Math.max(1, Math.min(200, Math.trunc(Number(params.searchLimit || 50) || 50)));

  if (activeDn && params.principalTypeFilter !== 'ou') {
    const response = await loadOuContent(
      fetchFn,
      {
        sourceId: params.selectedSourceId,
        dn: activeDn,
        query: q,
        scope: q ? 'subtree' : 'onelevel',
        enabledUsersOnly: true,
        limit
      },
      signal
    );

    const filtered = (response.items as PrincipalSearchItem[]).filter((item) =>
      principalTypeFilterPredicate(item, params.principalTypeFilter)
    );
    const eligible = filterIdentityRowsByImportPolicy(filtered, params.includeImportCandidates);
    return {
      rows: eligible,
      total: eligible.length
    };
  }

  const response = await searchIdentityDirectory(
    fetchFn,
    {
      sourceId: params.selectedSourceId,
      q,
      dn: activeDn || params.resolvedRootDn,
      scope: activeDn ? 'onelevel' : 'subtree',
      principalType: params.principalTypeFilter,
      enabledOnly: params.principalTypeFilter === 'user',
      limit
    },
    signal
  );

  const filtered = response.items.filter((item) => principalTypeFilterPredicate(item, params.principalTypeFilter));
  const eligible = filterIdentityRowsByImportPolicy(filtered, params.includeImportCandidates);
  return {
    rows: eligible,
    total: eligible.length
  };
}

export async function loadBrowserPreviewForRow(
  fetchFn: FetchLike,
  params: {
    selectedSourceId: number | null;
    item: PrincipalSearchItem;
    signal?: AbortSignal;
  }
): Promise<IdentityPreview | PrincipalSearchItem | null> {
  const dn = String(params.item?.dn ?? '').trim();
  const selectedSourceId = Number(params.selectedSourceId ?? 0);
  if (!dn || !Number.isFinite(selectedSourceId) || selectedSourceId <= 0) {
    return params.item;
  }

  const normalizedType = String(params.item?.type ?? '').toLowerCase();
  const principalType =
    normalizedType === 'user' || normalizedType === 'group' || normalizedType === 'ou' ? normalizedType : 'all';

  const preview = await loadIdentityPreview(
    fetchFn,
    {
      sourceId: selectedSourceId,
      dn,
      principalType
    },
    params.signal
  );

  return preview ?? params.item;
}
