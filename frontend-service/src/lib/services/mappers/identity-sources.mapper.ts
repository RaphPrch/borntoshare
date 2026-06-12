import { resolveStatusVariant, type StatusVariant } from '../../constants/status';

export type IdentitySourceRowLike = {
  id: number;
  type?: string;
  name?: string;
  display_name?: string;
  protocol?: 'ldap' | 'ldaps' | string;
  host?: string;
  port?: number;
  issuer_url?: string;
  base_dn?: string;
  bind_dn?: string;
  bind_password_ref?: string;
  client_id?: string;
  client_secret_ref?: string;
  status?: string;
  is_active?: boolean;
  used?: boolean;
  last_probe_at?: string | null;
  probed_at?: string | null;
  last_probe_message?: string | null;
  last_snapshot_at?: string | null;
  snapshot_at?: string | null;
  last_sync_at?: string | null;
  last_snapshot_status?: string | null;
  last_snapshot_version?: number | null;
  last_snapshot_objects_count?: number | null;
  last_snapshot_users_count?: number | null;
  last_snapshot_groups_count?: number | null;
  last_snapshot_memberships_count?: number | null;
  updated_at?: string | null;
  capabilities?: {
    auth?: boolean;
    import_groups?: boolean;
    auth_mode?: 'ntlm' | 'kerberos' | string;
    snapshot_enabled?: boolean;
  };
};

export type IdentitySourceUiRow = {
  id: number;
  name: string;
  type: string;
  status: string;
  endpoint: string;
  snapshot: string;
  used: boolean;
  raw: IdentitySourceRowLike;
};

export type IdentitySnapshotMetaLike = {
  status?: 'idle' | 'running' | 'success' | 'error' | string;
  loading?: boolean;
  lastRunAt?: string | null;
  lastSnapshotStatus?: string | null;
  lastSnapshotVersion?: number | null;
  lastSnapshotObjectsCount?: number | null;
  lastSnapshotUsersCount?: number | null;
  lastSnapshotGroupsCount?: number | null;
  lastSnapshotMembershipsCount?: number | null;
  note?: string | null;
  error?: string | null;
};

export type IdentitySourceCardVM = {
  id: number;
  name: string;
  subtitle: string;
  typeLabel: string;
  typeTone: 'ad' | 'oidc' | 'neutral';
  isLocal: boolean;
  supportsProbe: boolean;
  supportsSnapshot: boolean;
  healthLabel: string;
  healthTone: StatusVariant;
  snapshotLabel: string;
  snapshotTone: StatusVariant;
  endpointLabel: string;
  lastProbeLabel: string;
  lastSnapshotLabel: string;
  usersCount: number | null;
  groupsCount: number | null;
  membershipsCount: number | null;
  bindDn: string;
  issuer: string;
  isEnabled: boolean;
  neverSynced: boolean;
  raw: IdentitySourceRowLike;
};

export type IdentitySourceSummary = {
  total: number;
  healthy: number;
  issues: number;
  neverSynced: number;
};

export type IdentitySourceCardsComposition = {
  allCards: IdentitySourceCardVM[];
  filteredCards: IdentitySourceCardVM[];
  sortedCards: IdentitySourceCardVM[];
  summary: IdentitySourceSummary;
  selectedCard: IdentitySourceCardVM | null;
};

export type IdentitySourceSortKey =
  | 'name-asc'
  | 'name-desc'
  | 'health'
  | 'snapshot'
  | 'recent-probe';

const asLower = (value: unknown): string => String(value ?? '').trim().toLowerCase();

const statusLabel = (value: unknown): string => {
  const normalized = String(value ?? '').trim();
  if (!normalized) return 'Unknown';
  return normalized.replace(/[_-]+/g, ' ');
};

const toCount = (value: unknown): number | null => {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
};

const toIsoDate = (value: unknown): string | null => {
  const raw = String(value ?? '').trim();
  if (!raw) return null;
  const parsed = new Date(raw);
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
};

const toTimestamp = (value: unknown): number => {
  const iso = toIsoDate(value);
  if (!iso) return 0;
  const ms = new Date(iso).getTime();
  return Number.isFinite(ms) ? ms : 0;
};

const firstValidTimestamp = (...values: unknown[]): string | null => {
  for (const value of values) {
    const iso = toIsoDate(value);
    if (iso) return iso;
  }
  return null;
};

export const identitySourceTypeLabel = (value?: string): string => {
  const key = String(value ?? '').trim().toLowerCase();
  if (key === 'ad' || key === 'ldap') return 'Active Directory / LDAP';
  if (key === 'oidc') return 'OIDC';
  if (key === 'local') return 'Local';
  if (key === 'scim') return 'SCIM 2.0';
  return value ?? 'Identity source';
};

export const identitySourceDisplayLabel = (source: IdentitySourceRowLike): string =>
  source?.display_name ?? source?.name ?? 'Identity source';

export const normalizeIdentitySourceStatus = (status?: string, isActive?: boolean): string => {
  const key = String(status ?? '').trim().toLowerCase();
  if (key === 'disabled' && isActive) return 'connected';
  return key || (isActive ? 'connected' : 'disabled');
};

export const identitySourceStatusVariant = (source: IdentitySourceRowLike): StatusVariant =>
  resolveStatusVariant(normalizeIdentitySourceStatus(source?.status, source?.is_active));

export const formatRelativeTimestamp = (value?: string | null): string => {
  const iso = toIsoDate(value);
  if (!iso) return '—';
  const parsed = new Date(iso);
  const diffMs = Date.now() - parsed.getTime();
  if (!Number.isFinite(diffMs)) return '—';

  const minute = 60_000;
  const hour = 60 * minute;
  const day = 24 * hour;

  if (Math.abs(diffMs) < minute) return 'just now';
  if (Math.abs(diffMs) < hour) {
    const n = Math.max(1, Math.round(Math.abs(diffMs) / minute));
    return diffMs >= 0 ? `${n}m ago` : `in ${n}m`;
  }
  if (Math.abs(diffMs) < day) {
    const n = Math.max(1, Math.round(Math.abs(diffMs) / hour));
    return diffMs >= 0 ? `${n}h ago` : `in ${n}h`;
  }
  const n = Math.max(1, Math.round(Math.abs(diffMs) / day));
  return diffMs >= 0 ? `${n}d ago` : `in ${n}d`;
};

export const formatAbsoluteTimestamp = (value?: string | null): string => {
  const iso = toIsoDate(value);
  if (!iso) return '—';
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return '—';
  return parsed.toLocaleString('fr-FR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  });
};

export const formatIdentitySourceSubtitle = (source: IdentitySourceRowLike): string => {
  if (asLower(source?.type) === 'local') {
    return 'Local identity provider';
  }

  const baseDn = String(source?.base_dn ?? '').trim();
  const bindDn = String(source?.bind_dn ?? '').trim();
  const protocol = String(source?.protocol ?? '').trim().toUpperCase();

  if (baseDn && protocol) return `${protocol} · ${baseDn}`;
  if (baseDn) return baseDn;
  if (bindDn && protocol) return `${protocol} · ${bindDn}`;
  if (bindDn) return bindDn;
  if (protocol) return `${protocol} directory source`;
  return 'Directory source configuration';
};

export const getHealthTone = (status?: string | null, isEnabled = true): StatusVariant => {
  if (!isEnabled) return 'disabled';
  const normalized = asLower(status).replace(/[_\s-]+/g, '_');
  if (!normalized) return 'muted';
  if (['active', 'healthy', 'connected', 'online', 'success', 'succeeded'].includes(normalized)) return 'success';
  if (['warning', 'stale', 'degraded', 'queued', 'pending'].includes(normalized)) return 'warning';
  if (['running', 'probing', 'processing', 'in_progress'].includes(normalized)) return 'info';
  if (['error', 'failed', 'offline', 'disconnected', 'timeout', 'unreachable'].includes(normalized)) return 'error';
  return resolveStatusVariant(normalized);
};

const healthLabelFromSource = (status?: string | null, isEnabled = true): string => {
  if (!isEnabled) return 'Disabled';
  const normalized = asLower(status).replace(/[_\s-]+/g, '_');
  if (!normalized) return 'Unknown';
  if (['active', 'healthy', 'connected', 'online', 'success', 'succeeded'].includes(normalized)) return 'Healthy';
  if (['warning', 'stale', 'degraded'].includes(normalized)) return 'Degraded';
  if (['running', 'probing', 'processing', 'in_progress'].includes(normalized)) return 'Checking';
  if (['error', 'failed', 'offline', 'disconnected', 'timeout', 'unreachable'].includes(normalized)) return 'Unhealthy';
  return statusLabel(status);
};

export const getSnapshotTone = (
  status?: string | null,
  lastSnapshotAt?: string | null,
  snapshotJobStatus?: string | null
): StatusVariant => {
  const job = asLower(snapshotJobStatus);
  if (job === 'running') return 'info';
  if (job === 'error') return 'error';

  const normalized = asLower(status).replace(/[_\s-]+/g, '_');
  if (!normalized && !toIsoDate(lastSnapshotAt)) return 'muted';
  if (['active', 'success', 'succeeded', 'synced', 'up_to_date'].includes(normalized)) return 'success';
  if (['running', 'queued', 'processing', 'in_progress'].includes(normalized)) return 'info';
  if (['warning', 'stale', 'needs_refresh', 'partial'].includes(normalized)) return 'warning';
  if (['failed', 'error', 'cancelled', 'canceled'].includes(normalized)) return 'error';
  return resolveStatusVariant(normalized);
};

const snapshotLabelFromSource = (
  status?: string | null,
  lastSnapshotAt?: string | null,
  snapshotJobStatus?: string | null
): string => {
  const job = asLower(snapshotJobStatus);
  if (job === 'running') return 'Snapshot in progress';

  const normalized = String(status ?? '').trim();
  const relative = formatRelativeTimestamp(lastSnapshotAt);

  if (!normalized && !toIsoDate(lastSnapshotAt)) return 'Never Synced';
  if (normalized && relative !== '—') return `${statusLabel(normalized)} · ${relative}`;
  if (normalized) return statusLabel(normalized);
  if (relative !== '—') return `Synced ${relative}`;
  return 'No snapshot metadata';
};

const endpointFromSource = (source: IdentitySourceRowLike): string => {
  if (asLower(source?.type) === 'local') return 'Local provider';

  const host = String(source?.host ?? '').trim();
  const issuer = String(source?.issuer_url ?? '').trim();
  const port = Number(source?.port ?? 0);
  if (host) return `${host}${Number.isFinite(port) && port > 0 ? `:${port}` : ''}`;
  if (issuer) return issuer;
  return 'No endpoint';
};

const typeToneFromSource = (sourceType?: string): 'ad' | 'oidc' | 'neutral' => {
  const key = asLower(sourceType);
  if (key === 'ad' || key === 'ldap') return 'ad';
  if (key === 'oidc') return 'oidc';
  return 'neutral';
};

const statusWeight = (tone: StatusVariant): number => {
  if (tone === 'error') return 4;
  if (tone === 'warning') return 3;
  if (tone === 'info') return 2;
  if (tone === 'muted' || tone === 'disabled') return 1;
  return 0;
};

export const mapIdentitySourceToCardVM = (
  source: IdentitySourceRowLike,
  options?: {
    snapshotMeta?: IdentitySnapshotMetaLike | null;
    probeJobStatus?: string | null;
    snapshotJobStatus?: string | null;
  }
): IdentitySourceCardVM => {
  const snapshotMeta = options?.snapshotMeta ?? null;
  const sourceType = asLower(source?.type);
  const isLocal = sourceType === 'local';
  const isAdCompatible = sourceType === 'ad' || sourceType === 'ldap';
  const snapshotEnabled = source?.capabilities?.snapshot_enabled === true;
  const supportsProbe = isAdCompatible;
  const supportsSnapshot = isAdCompatible && snapshotEnabled;

  const snapshotStatus =
    String(snapshotMeta?.lastSnapshotStatus ?? source?.last_snapshot_status ?? '').trim() || null;
  const snapshotAt = firstValidTimestamp(
    snapshotMeta?.lastRunAt,
    source?.last_snapshot_at,
    source?.snapshot_at,
    source?.last_sync_at,
    source?.updated_at
  );
  const isEnabled = Boolean(source?.is_active ?? true);

  const sourceStatus = normalizeIdentitySourceStatus(source?.status, isEnabled);
  const probeJobStatus = String(options?.probeJobStatus ?? '').trim().toLowerCase();

  const healthTone: StatusVariant =
    probeJobStatus === 'running'
      ? 'info'
      : getHealthTone(sourceStatus, isEnabled);
  const healthLabel =
    probeJobStatus === 'running'
      ? 'Probe running'
      : healthLabelFromSource(sourceStatus, isEnabled);

  const snapshotTone =
    supportsSnapshot
      ? getSnapshotTone(snapshotStatus, snapshotAt, options?.snapshotJobStatus ?? null)
      : 'muted';
  const snapshotLabel =
    supportsSnapshot
      ? snapshotLabelFromSource(snapshotStatus, snapshotAt, options?.snapshotJobStatus ?? null)
      : 'Not applicable';

  const usersCount =
    toCount(snapshotMeta?.lastSnapshotUsersCount) ?? toCount(source?.last_snapshot_users_count);
  const groupsCount =
    toCount(snapshotMeta?.lastSnapshotGroupsCount) ?? toCount(source?.last_snapshot_groups_count);
  const membershipsCount =
    toCount(snapshotMeta?.lastSnapshotMembershipsCount) ??
    toCount(source?.last_snapshot_memberships_count);

  const lastProbeAt = firstValidTimestamp(
    source?.last_probe_at,
    source?.probed_at,
    source?.updated_at
  );

  const lastProbeLabel =
    probeJobStatus === 'running'
      ? 'Probe in progress'
      : lastProbeAt
        ? `${formatAbsoluteTimestamp(lastProbeAt)} (${formatRelativeTimestamp(lastProbeAt)})`
        : 'Never';

  const lastSnapshotLabel = snapshotAt
    ? `${formatAbsoluteTimestamp(snapshotAt)} (${formatRelativeTimestamp(snapshotAt)})`
    : 'No snapshot yet';

  return {
    id: Number(source?.id ?? 0),
    name: identitySourceDisplayLabel(source),
    subtitle: formatIdentitySourceSubtitle(source),
    typeLabel: identitySourceTypeLabel(source?.type),
    typeTone: typeToneFromSource(source?.type),
    isLocal,
    supportsProbe,
    supportsSnapshot,
    healthLabel,
    healthTone,
    snapshotLabel,
    snapshotTone,
    endpointLabel: endpointFromSource(source),
    lastProbeLabel: supportsProbe
      ? lastProbeLabel
      : 'Not applicable',
    lastSnapshotLabel: supportsSnapshot
      ? lastSnapshotLabel
      : 'Not applicable',
    usersCount,
    groupsCount,
    membershipsCount,
    bindDn: String(source?.bind_dn ?? '').trim() || '—',
    issuer: String(source?.issuer_url ?? '').trim() || '—',
    isEnabled,
    neverSynced: supportsSnapshot ? (!snapshotStatus && !toIsoDate(snapshotAt)) : false,
    raw: source
  };
};

export const filterIdentitySourcesByQuery = <T extends IdentitySourceRowLike>(
  sources: T[],
  query: string
): T[] => {
  const q = String(query ?? '').trim().toLowerCase();
  if (!q) return Array.isArray(sources) ? sources : [];

  return (Array.isArray(sources) ? sources : []).filter((source) =>
    [
      source?.display_name,
      source?.name,
      source?.type,
      source?.host,
      source?.issuer_url,
      source?.base_dn,
      source?.bind_dn
    ]
      .map((v) => String(v ?? '').toLowerCase())
      .join(' ')
      .includes(q)
  );
};

export const filterIdentitySourceCards = (
  cards: IdentitySourceCardVM[],
  filters: {
    query?: string;
    type?: string;
    status?: string;
    snapshot?: string;
  }
): IdentitySourceCardVM[] => {
  const query = String(filters?.query ?? '').trim().toLowerCase();
  const type = String(filters?.type ?? 'all').trim().toLowerCase();
  const status = String(filters?.status ?? 'all').trim().toLowerCase();
  const snapshot = String(filters?.snapshot ?? 'all').trim().toLowerCase();

  return (Array.isArray(cards) ? cards : []).filter((card) => {
    if (query) {
      const haystack = [
        card.name,
        card.subtitle,
        card.typeLabel,
        card.endpointLabel,
        card.raw?.host,
        card.raw?.issuer_url,
        card.raw?.base_dn,
        card.raw?.bind_dn
      ]
        .map((value) => String(value ?? '').toLowerCase())
        .join(' ');
      if (!haystack.includes(query)) return false;
    }

    if (type !== 'all') {
      const cardType = asLower(card.raw?.type);
      if (cardType !== type) return false;
    }

    if (status !== 'all') {
      if (status === 'healthy' && card.healthTone !== 'success') return false;
      if (status === 'issues' && !['warning', 'error'].includes(card.healthTone)) return false;
      if (status === 'disabled' && card.isEnabled) return false;
      if (status === 'unknown' && card.healthTone !== 'muted') return false;
    }

    if (snapshot !== 'all') {
      if (snapshot === 'synced' && card.snapshotTone !== 'success') return false;
      if (snapshot === 'never' && !card.neverSynced) return false;
      if (snapshot === 'failed' && card.snapshotTone !== 'error') return false;
      if (snapshot === 'running' && card.snapshotTone !== 'info') return false;
    }

    return true;
  });
};

export const sortIdentitySourceCards = (
  cards: IdentitySourceCardVM[],
  sortBy: IdentitySourceSortKey
): IdentitySourceCardVM[] => {
  const rows = [...(Array.isArray(cards) ? cards : [])];
  if (sortBy === 'name-desc') {
    rows.sort((a, b) => b.name.localeCompare(a.name, undefined, { sensitivity: 'base', numeric: true }));
    return rows;
  }
  if (sortBy === 'health') {
    rows.sort((a, b) => {
      const byHealth = statusWeight(b.healthTone) - statusWeight(a.healthTone);
      if (byHealth !== 0) return byHealth;
      return a.name.localeCompare(b.name, undefined, { sensitivity: 'base', numeric: true });
    });
    return rows;
  }
  if (sortBy === 'snapshot') {
    rows.sort((a, b) => {
      const bySnapshot = statusWeight(b.snapshotTone) - statusWeight(a.snapshotTone);
      if (bySnapshot !== 0) return bySnapshot;
      return a.name.localeCompare(b.name, undefined, { sensitivity: 'base', numeric: true });
    });
    return rows;
  }
  if (sortBy === 'recent-probe') {
    rows.sort((a, b) => {
      const left = toTimestamp(a.raw?.last_probe_at);
      const right = toTimestamp(b.raw?.last_probe_at);
      if (right !== left) return right - left;
      return a.name.localeCompare(b.name, undefined, { sensitivity: 'base', numeric: true });
    });
    return rows;
  }
  rows.sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base', numeric: true }));
  return rows;
};

export const buildIdentitySourceSummary = (cards: IdentitySourceCardVM[]): IdentitySourceSummary => {
  const rows = Array.isArray(cards) ? cards : [];
  return {
    total: rows.length,
    healthy: rows.filter((card) => card.healthTone === 'success').length,
    issues: rows.filter((card) => ['warning', 'error'].includes(card.healthTone)).length,
    neverSynced: rows.filter((card) => card.neverSynced).length
  };
};

export const composeIdentitySourceCards = (
  sources: IdentitySourceRowLike[],
  options?: {
    snapshotMetaBySourceId?: Record<number, IdentitySnapshotMetaLike | null | undefined>;
    probeJobStatusBySourceId?: Record<number, string | null | undefined>;
    snapshotJobStatusBySourceId?: Record<number, string | null | undefined>;
    filters?: {
      query?: string;
      type?: string;
      status?: string;
      snapshot?: string;
    };
    sortBy?: IdentitySourceSortKey;
    selectedSourceId?: number | null;
  }
): IdentitySourceCardsComposition => {
  const rows = Array.isArray(sources) ? sources : [];
  const allCards = rows.map((source) => {
    const sourceId = Number(source?.id ?? 0);
    return mapIdentitySourceToCardVM(source, {
      snapshotMeta: options?.snapshotMetaBySourceId?.[sourceId] ?? null,
      probeJobStatus: options?.probeJobStatusBySourceId?.[sourceId] ?? null,
      snapshotJobStatus: options?.snapshotJobStatusBySourceId?.[sourceId] ?? null
    });
  });

  const filteredCards = filterIdentitySourceCards(allCards, {
    query: options?.filters?.query,
    type: options?.filters?.type,
    status: options?.filters?.status,
    snapshot: options?.filters?.snapshot
  });

  const sortedCards = sortIdentitySourceCards(filteredCards, options?.sortBy ?? 'name-asc');
  const summary = buildIdentitySourceSummary(allCards);

  const selectedSourceId = Number(options?.selectedSourceId ?? 0);
  const selectedCard =
    selectedSourceId > 0
      ? allCards.find((card) => Number(card.id) === selectedSourceId) ?? null
      : null;

  return {
    allCards,
    filteredCards,
    sortedCards,
    summary,
    selectedCard
  };
};

export const mapIdentitySourceRows = (
  sources: IdentitySourceRowLike[],
  sourceSnapshotLabel: (sourceId: number) => string
): IdentitySourceUiRow[] =>
  (Array.isArray(sources) ? sources : []).map((source) => {
    const vm = mapIdentitySourceToCardVM(source);
    return {
      id: vm.id,
      name: vm.name,
      type: vm.typeLabel,
      status: normalizeIdentitySourceStatus(source?.status, source?.is_active),
      endpoint: vm.endpointLabel,
      snapshot: sourceSnapshotLabel(Number(source?.id ?? 0)) || vm.snapshotLabel,
      used: Boolean(source?.used),
      raw: source
    };
  });
