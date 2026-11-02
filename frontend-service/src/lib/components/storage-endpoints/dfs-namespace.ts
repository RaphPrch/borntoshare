import { t } from '$lib/i18n';
import { apiGetData, apiPostData } from '$lib/api/client';
import { humanizeFileServerMessage } from '$lib/errors/file-server';
import { runProbeWithPolling } from '$lib/jobs/probe-runner';

/** A DFS namespace as read by BornToShare: its DFS folders and the file server folders they lead to. */
export type DfsTarget = {
  unc: string;
  server: string;
  storage_endpoint_id: number | null;
  storage_endpoint_name: string | null;
  storage_root_id: number | null;
};
export type DfsLink = {
  path: string;
  dfs_path: string;
  targets: DfsTarget[];
  state: 'managed' | 'partial' | 'to_manage' | 'unknown_server' | 'no_target';
};
export type DfsInfo = {
  path: string | null;
  type: string | null;
  root_targets: string[];
  read_at: string | null;
  error: string | null;
  links: DfsLink[];
};

export type DfsCounts = {
  all: number;
  managed: number;
  todo: number;
  unknown: number;
  noTarget: number;
  servers: number;
  unknownServers: string[];
};

const STALE_DAYS = 7;

export function dfsCounts(info: DfsInfo | null): DfsCounts {
  const links = info?.links ?? [];
  const unknownServers = [
    ...new Set(
      links.flatMap((link) => link.targets.filter((target) => !target.storage_endpoint_id).map((target) => target.server.toUpperCase()))
    )
  ];
  return {
    all: links.length,
    managed: links.filter((link) => link.state === 'managed').length,
    todo: links.filter((link) => link.state === 'to_manage' || link.state === 'partial').length,
    unknown: links.filter((link) => link.state === 'unknown_server').length,
    noTarget: links.filter((link) => link.state === 'no_target').length,
    servers: new Set(links.flatMap((link) => link.targets.map((target) => target.server.toLowerCase()))).size,
    unknownServers
  };
}

/** Days since the last read, or null when never read. */
export function dfsReadAge(info: DfsInfo | null, now = Date.now()): number | null {
  const at = Date.parse(String(info?.read_at ?? ''));
  return Number.isFinite(at) ? Math.floor((now - at) / 86_400_000) : null;
}

export const dfsReadIsStale = (info: DfsInfo | null): boolean => {
  const age = dfsReadAge(info);
  return age === null || age >= STALE_DAYS;
};

export const loadDfsInfo = (fetchFn: typeof fetch, endpointId: number) =>
  apiGetData<DfsInfo>(fetchFn, `/storage-endpoints/${endpointId}/dfs-links`);

/** Read the namespace again on its server (worker), then save what was read. */
export async function readDfsAgain(fetchFn: typeof fetch, endpoint: Record<string, any>, path: string, type: string | null = null): Promise<void> {
  // \\corp.local\brest: the worker needs the domain to give back the domain path, not the one of its root server
  const domain = type === 'domain' ? path.split(/[\\/]+/).filter(Boolean)[0] ?? '' : '';
  const id = Number(endpoint?.id ?? endpoint?.storage_endpoint_id ?? 0);
  const final: any = await runProbeWithPolling({
    fetchFn,
    request: {
      kind: 'storage-endpoint',
      protocol: 'dfs',
      scope: 'read',
      target: { host: String(endpoint.host ?? ''), port: Number(endpoint.port ?? 445), path, ...(domain ? { domain } : {}) },
      auth: { mode: 'ntlm', username: String(endpoint.bind_dn ?? endpoint.auth_username ?? ''), secret_ref: String(endpoint.bind_password_ref ?? endpoint.auth_secret_ref ?? '') },
      options: { timeout_sec: 120 },
      context: { ui_origin: 'admin', storage_endpoint_id: id }
    } as any,
    intervalMs: 1500,
    maxAttempts: 100
  });
  if (!final.ok) throw new Error(humanizeFileServerMessage(t(String(final.errorMessage ?? final.result?.message ?? 'The DFS server could not be read'))));
  const namespace = (final.result?.details?.namespaces ?? [])[0];
  if (!namespace) throw new Error(t('This namespace was not found on its server.'));
  await apiPostData(fetchFn, `/storage-endpoints/${id}/dfs-snapshot`, { namespace });
}

/** Manage DFS folders: their target folders become storage roots, on every target. */
export const manageDfsLinks = (fetchFn: typeof fetch, endpointId: number, paths: string[]) =>
  apiPostData<{ managed: { path: string; created: number[] }[]; failed: { path: string; message: string }[] }>(
    fetchFn,
    `/storage-endpoints/${endpointId}/dfs-links/manage`,
    { paths }
  );
