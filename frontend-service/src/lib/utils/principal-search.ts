export type PrincipalSearchItem = {
  id: string | number;
  identity_id?: number | null;
  type?: PrincipalType;
  username?: string | null;
  upn?: string | null;
  display_name?: string | null;
  email?: string | null;
  ou?: string | null;
  group_count?: number;
  enabled?: boolean;
  auth_source?: string | null;
  external_id?: string | null;
  dn?: string | null;
  identity_source_id?: number | null;
  is_active?: boolean;
  browse_status?: 'up_to_date' | 'needs_refresh' | null;
  is_import_candidate?: boolean;
};

export type PrincipalType = 'user' | 'group' | 'ou' | 'all' | string;

type RawPrincipalRow = Record<string, unknown>;

const asText = (value: unknown) => String(value ?? '').trim();

const normalizePrincipalType = (value: unknown): PrincipalType =>
  String(value ?? 'user').trim().toLowerCase() || 'user';

const normalizePrincipalIdentitySourceId = (value: unknown): number | null => {
  const parsed = Number(value ?? 0);
  if (!Number.isFinite(parsed) || parsed <= 0) return null;
  return Math.trunc(parsed);
};

const normalizePrincipalIdentityId = (row: RawPrincipalRow): number | null => {
  const parsed = Number(
    row?.identity_id ??
      (row?.identity as Record<string, unknown> | null | undefined)?.identity_id ??
      (row?.identity as Record<string, unknown> | null | undefined)?.id ??
      0
  );
  if (!Number.isFinite(parsed) || parsed <= 0) return null;
  return Math.trunc(parsed);
};

const resolvePrincipalStableId = (row: RawPrincipalRow, identityId: number | null): string | number | null => {
  const candidates = [
    row?.id,
    row?.external_id,
    row?.dn,
    row?.username,
    row?.upn,
    row?.email,
    row?.display_name,
    identityId
  ];

  for (const candidate of candidates) {
    if (typeof candidate === 'number' && Number.isFinite(candidate) && candidate > 0) {
      return Math.trunc(candidate);
    }
    const text = String(candidate ?? '').trim();
    if (text) return text;
  }

  return null;
};

const normalizePrincipalBrowseStatus = (value: unknown): 'up_to_date' | 'needs_refresh' | null => {
  const normalized = String(value ?? '').trim().toLowerCase();
  if (normalized === 'up_to_date') return 'up_to_date';
  if (normalized === 'needs_refresh') return 'needs_refresh';
  return null;
};

const toPrincipalSearchItem = (row: RawPrincipalRow): PrincipalSearchItem | null => {
  const identityId = normalizePrincipalIdentityId(row);
  const stableId = resolvePrincipalStableId(row, identityId);
  const stableIdValue =
    typeof stableId === 'string'
      ? stableId.trim()
      : typeof stableId === 'number' && Number.isFinite(stableId)
        ? Math.trunc(stableId)
        : null;
  if (stableIdValue === null || String(stableIdValue).length === 0) return null;

  return {
    id: stableIdValue,
    identity_id: identityId,
    type: normalizePrincipalType(row?.type ?? row?.principal_type),
    username: (row?.username as string | null | undefined) ?? null,
    upn: (row?.upn as string | null | undefined) ?? null,
    display_name: (row?.display_name as string | null | undefined) ?? null,
    email: ((row?.email ?? row?.mail) as string | null | undefined) ?? null,
    ou: (row?.ou as string | null | undefined) ?? null,
    group_count: Number(row?.group_count ?? 0) || 0,
    enabled: typeof row?.enabled === 'boolean' ? (row.enabled as boolean) : undefined,
    auth_source: (row?.auth_source as string | null | undefined) ?? null,
    external_id: (row?.external_id as string | null | undefined) ?? null,
    dn: (row?.dn as string | null | undefined) ?? null,
    identity_source_id: normalizePrincipalIdentitySourceId(
      row?.identity_source_id ??
      (row?.identity as Record<string, unknown> | null | undefined)?.identity_source_id
    ),
    is_active: typeof row?.is_active === 'boolean' ? (row.is_active as boolean) : undefined,
    browse_status: normalizePrincipalBrowseStatus(row?.browse_status ?? row?.status),
    is_import_candidate: Boolean(row?.is_import_candidate)
  };
};

const escapeHtml = (value: string) =>
  value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');

export const principalKey = (item: Record<string, unknown>) =>
  asText(
    item.external_id ??
      item.id ??
      item.dn ??
      item.username ??
      item.upn ??
      item.email ??
      item.display_name ??
      ''
  ).toLowerCase();

export const principalLabel = (item: Record<string, unknown>): string =>
  asText(item.display_name ?? item.username ?? item.dn ?? item.id ?? 'Identity');

export const principalSubtitle = (item: Record<string, unknown>): string => {
  const normalizedType = String(item.type ?? 'user').toLowerCase();
  const kind =
    normalizedType === 'group'
      ? 'AD Group'
      : normalizedType === 'ou'
        ? 'OU'
        : 'User';
  const login = asText(item.username ?? item.upn);
  const source = asText(item.auth_source);
  const browseStatus = asText(item.browse_status ?? item.status).toLowerCase();
  const refreshPart =
    browseStatus === 'up_to_date'
      ? 'Up-to-date'
      : browseStatus === 'needs_refresh'
        ? 'Needs refresh'
        : '';
  if (login && source) return `${kind} · ${login} · ${source}`;
  if (login && refreshPart) return `${kind} · ${login} · ${refreshPart}`;
  if (login) return `${kind} · ${login}`;
  if (source) return `${kind} · ${source}`;
  return kind;
};

export const highlightMatch = (value: unknown, query: string): string => {
  const raw = asText(value);
  if (!raw) return '-';
  const safeRaw = escapeHtml(raw);
  const q = asText(query);
  if (!q) return safeRaw;

  const escaped = q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const re = new RegExp(escaped, 'ig');
  return safeRaw.replace(re, (m) => `<mark>${m}</mark>`);
};

export const normalizePrincipalList = (payload: unknown): PrincipalSearchItem[] => {
  if (Array.isArray(payload)) {
    return payload
      .map((item) => toPrincipalSearchItem(item as RawPrincipalRow))
      .filter((item): item is PrincipalSearchItem => Boolean(item));
  }

  const root = payload && typeof payload === 'object' ? (payload as Record<string, unknown>) : null;
  const source = Array.isArray(root?.items)
    ? root.items
    : [
        ...(Array.isArray(root?.users) ? root.users : []),
        ...(Array.isArray(root?.groups) ? root.groups : [])
      ];

  if (!Array.isArray(source)) return [];

  return source
      .map((item) => toPrincipalSearchItem(item as RawPrincipalRow))
      .filter((item): item is PrincipalSearchItem => Boolean(item))
    .filter((item: PrincipalSearchItem) => String(item.id ?? '').trim().length > 0);
};

export const filterPrincipals = (rows: PrincipalSearchItem[], q: string, limit = 24): PrincipalSearchItem[] => {
  const query = asText(q).toLowerCase();
  if (!query) return rows.slice(0, limit);

  return rows
    .filter((item) => {
      const haystack = [item.display_name, item.username, item.email, item.auth_source]
        .map((v) => String(v ?? '').toLowerCase())
        .join(' ');
      return haystack.includes(query);
    })
    .slice(0, limit);
};
