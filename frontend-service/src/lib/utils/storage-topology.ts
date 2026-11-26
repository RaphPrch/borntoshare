/**
 * Storage Topology: where one is (in the address), how a state reads, what is known of the capacity. Pure, tested.
 */

/** Where one is: a zone, then a server or a DFS namespace, then a volume and/or a share of the server. */
export type TopologyPlace = { zone?: number | null; server?: number | null; dfs?: number | null; volume?: string | null; share?: string | null };

const positive = (value: string | null) => {
  const n = Number(value);
  return Number.isInteger(n) && n > 0 ? n : null;
};

/** The place from the address. A server and a DFS namespace exclude each other; a share or a volume needs a server. */
export function topologyLevel(params: URLSearchParams): TopologyPlace {
  const zone = positive(params.get('zone'));
  const server = zone ? positive(params.get('server')) : null;
  const dfs = zone && !server ? positive(params.get('dfs')) : null;
  const volume = server && /^[A-Za-z]:$/.test(params.get('volume') ?? '') ? params.get('volume')!.toUpperCase() : null;
  const share = server ? params.get('share') || null : null;
  return { zone, server, dfs, volume, share };
}

export function topologyHref(place: TopologyPlace): string {
  const params = new URLSearchParams();
  if (place.zone) params.set('zone', String(place.zone));
  if (place.zone && place.server) params.set('server', String(place.server));
  else if (place.zone && place.dfs) params.set('dfs', String(place.dfs));
  if (place.server && place.volume) params.set('volume', place.volume);
  if (place.server && place.share) params.set('share', place.share);
  const query = params.toString();
  return `/admin/storage-topology${query ? `?${query}` : ''}`;
}

export const STATE_META: Record<string, { label: string; variant: 'success' | 'error' | 'warning' | 'muted' }> = {
  available: { label: 'Available', variant: 'success' },
  unavailable: { label: 'Unavailable', variant: 'error' },
  degraded: { label: 'Degraded', variant: 'warning' },
  unknown: { label: 'Unknown', variant: 'muted' }
};

export const DFS_LINK_LABEL: Record<string, string> = {
  managed: 'Managed', partial: 'Partly managed', to_manage: 'To manage', unknown_server: 'Server not declared', no_target: 'No target'
};

type Capacity = { quota_limit_bytes?: number | null; quota_used_bytes?: number | null; measured_bytes?: number | null } | null | undefined;

/** What is known of the space: the quotas read (used / limit), else the measured size; '' when nothing is known. */
export function capacityLine(
  capacity: Capacity,
  fmt: (bytes: unknown) => string = (bytes) => String(bytes),
  tr: (key: string, vars?: Record<string, unknown>) => string = (key, vars = {}) => key.replace(/\{(\w+)\}/g, (_, k) => String(vars[k]))
): string {
  if (!capacity) return '';
  if (capacity.quota_limit_bytes != null) {
    return tr('{used} of {limit} (quotas)', { used: fmt(capacity.quota_used_bytes ?? 0), limit: fmt(capacity.quota_limit_bytes) });
  }
  if (capacity.measured_bytes != null) return tr('{size} measured', { size: fmt(capacity.measured_bytes) });
  return '';
}
