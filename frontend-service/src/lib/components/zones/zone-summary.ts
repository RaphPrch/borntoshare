import type { GovernanceAlert } from '$lib/api/governance-alerts';
import {
  alertTitle,
  storageRootAlertRootId,
  storageRootAlertTone,
  visibleStorageRootAlerts
} from '$lib/mappers/storage-root-alerts.mapper';

/**
 * What a zone needs: its servers reachable or not, and its folders to review, read from the open alerts
 * of its storage roots. Shared by the tiles, « To do on this zone » and the cards of the zone page.
 */
export type ZoneServer = {
  id: number;
  name: string;
  host: string;
  dfs: boolean;
  state: 'reachable' | 'unreachable' | 'checking' | 'disabled' | 'unknown';
  lastProbeAt: string | null;
  roots: number;
  review: number;
};

export type ZoneRoot = {
  id: number;
  name: string;
  path: string;
  endpointId: number;
  blocking: boolean;
  noGuardian: boolean;
  reread: boolean;
  pending: boolean;
  review: boolean;
  label: string;
};

export type ZoneSummary = {
  servers: ZoneServer[];
  files: ZoneServer[];
  dfs: ZoneServer[];
  reachable: number;
  unreachable: ZoneServer[];
  roots: ZoneRoot[];
  review: ZoneRoot[];
  noGuardian: ZoneRoot[];
  reread: ZoneRoot[];
};

const PROBE_OR_ACL = ['root_probe_failed', 'root_probe_unknown', 'acl_principal_not_governed', 'acl_profile_missing', 'ad_group_read_failed'];

const num = (value: unknown): number => {
  const n = Number(value ?? 0);
  return Number.isFinite(n) && n > 0 ? n : 0;
};

export function summarizeZone(
  endpoints: any[],
  storageRoots: any[],
  alerts: GovernanceAlert[],
  runtimeState: (endpointId: number) => string | null = () => null
): ZoneSummary {
  const byRoot = new Map<number, GovernanceAlert[]>();
  for (const alert of visibleStorageRootAlerts(alerts)) {
    if (String(alert?.status ?? 'open').toLowerCase() !== 'open') continue;
    const id = storageRootAlertRootId(alert);
    if (!id) continue;
    if (!byRoot.has(id)) byRoot.set(id, []);
    byRoot.get(id)!.push(alert);
  }

  const servers: ZoneServer[] = endpoints.map((ep) => {
    const id = num(ep?.id ?? ep?.storage_endpoint_id);
    const raw = runtimeState(id) ?? String(ep?.operational_state ?? '').toLowerCase();
    const state = (['reachable', 'unreachable', 'checking', 'disabled'].includes(raw) ? raw : 'unknown') as ZoneServer['state'];
    return {
      id,
      name: String(ep?.name ?? ep?.storage_endpoint_name ?? id),
      host: String(ep?.host ?? ''),
      dfs: String(ep?.endpoint_type ?? '').toLowerCase() === 'dfs',
      state,
      lastProbeAt: ep?.last_probe_at ? String(ep.last_probe_at) : null,
      roots: 0,
      review: 0
    };
  });
  const serverById = new Map(servers.map((server) => [server.id, server]));

  const roots: ZoneRoot[] = storageRoots.map((root) => {
    const id = num(root?.id ?? root?.storage_root_id);
    const endpointId = num(root?.storage_endpoint_id);
    const list = byRoot.get(id) ?? [];
    const types = list.map((alert) => String(alert?.alert_type ?? '').toLowerCase());
    const blocking = list.some((alert) => storageRootAlertTone(alert) === 'error');
    const serverDown = serverById.get(endpointId)?.state === 'unreachable';
    const worst = [...list].sort((a, b) => Number(storageRootAlertTone(b) === 'error') - Number(storageRootAlertTone(a) === 'error'))[0];
    const entry: ZoneRoot = {
      id,
      name: String(root?.name ?? root?.storage_root_name ?? id),
      path: String(root?.root_path ?? ''),
      endpointId,
      blocking,
      noGuardian: types.includes('missing_guardian'),
      // Read again only where the server answers: an unreachable server is settled first
      reread: !serverDown && types.some((type) => PROBE_OR_ACL.includes(type)),
      pending: types.includes('pending_access_validation'),
      review: list.length > 0,
      label: worst ? alertTitle(worst) : ''
    };
    const server = serverById.get(endpointId);
    if (server) {
      server.roots += 1;
      if (entry.review) server.review += 1;
    }
    return entry;
  });

  const files = servers.filter((server) => !server.dfs);
  const review = roots
    .filter((root) => root.review)
    .sort((a, b) => Number(b.blocking) - Number(a.blocking) || Number(b.pending) - Number(a.pending) || a.name.localeCompare(b.name, 'fr'));
  return {
    servers,
    files,
    dfs: servers.filter((server) => server.dfs),
    reachable: files.filter((server) => server.state === 'reachable').length,
    unreachable: files.filter((server) => server.state === 'unreachable'),
    roots,
    review,
    noGuardian: roots.filter((root) => root.noGuardian),
    reread: roots.filter((root) => root.reread)
  };
}
