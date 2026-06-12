import type { FetchLike } from '../api/client';
import { apiGetData, apiGetList, apiPost } from '../api/client';
import { getProbeJob, runProbeJob, type ProbeRunRequest } from '../api/probes';
import { pushUiActivityLog } from '../core/logging';
import { normalizeProbeStatus } from '../services/mappers/visual-state.mapper';
import { normalizeProbeError, type NormalizedProbeError } from './probe-errors';
import { logProbeResult, logProbeStart } from './probe-logger';

export type ProbeSnapshot = {
  status: string;
  ok?: boolean;
  result?: any;
};

export type ProbeRunResult<TPost = unknown> = {
  jobId: string;
  status: string;
  ok: boolean;
  result?: any;
  errorMessage?: string;
  postCheck?: TPost;
};

export type RunProbeWithPollingOptions<TPost = unknown> = {
  fetchFn: FetchLike;
  request: ProbeRunRequest;
  intervalMs?: number;
  maxAttempts?: number;
  onUpdate?: (snapshot: ProbeSnapshot) => void;
  afterSuccess?: (result: any) => Promise<TPost>;
};

export type RunCapsuleProbeOptions<TPost = unknown> = {
  fetchFn: FetchLike;
  request: ProbeRunRequest;
  intervalMs?: number;
  maxAttempts?: number;
  onUpdate?: (snapshot: { status: string; ok?: boolean; result?: unknown }) => void;
  afterSuccess?: (result: unknown) => Promise<TPost>;
};

export type RunCapsuleProbeSuccess<TPost = unknown> = {
  ok: true;
  result: ProbeRunResult<TPost>;
  error?: never;
};

export type RunCapsuleProbeFailure = {
  ok: false;
  error: NormalizedProbeError;
  result?: ProbeRunResult<unknown>;
};

const isRunningStatus = (status: string) => normalizeProbeStatus(String(status ?? '')) === 'running';
const isSuccessStatus = (status: string) => normalizeProbeStatus(String(status ?? '')) === 'success';

export async function runProbeWithPolling<TPost = unknown>(
  options: RunProbeWithPollingOptions<TPost>
): Promise<ProbeRunResult<TPost>> {
  const {
    fetchFn,
    request,
    intervalMs = 1500,
    maxAttempts = 40,
    onUpdate,
    afterSuccess
  } = options;

  const started = await runProbeJob(fetchFn, request);
  const jobId = String(started?.job_id ?? '').trim();
  if (!jobId) {
    throw new Error('Missing job_id from probe run');
  }

  for (let attempt = 0; attempt <= maxAttempts; attempt++) {
    const job = await getProbeJob(fetchFn, jobId);
    const status = String(job?.status ?? 'unknown').toLowerCase();
    const ok = isSuccessStatus(status) || job?.result?.success === true;

    onUpdate?.({ status, ok: isSuccessStatus(status) ? ok : undefined, result: job?.result });

    if (!isRunningStatus(status)) {
      const base: ProbeRunResult<TPost> = {
        jobId,
        status,
        ok,
        result: job?.result,
        errorMessage: job?.error?.message
      };

      if (ok && afterSuccess) {
        base.postCheck = await afterSuccess(job?.result);
      }

      return base;
    }

    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }

  return {
    jobId,
    status: 'timeout',
    ok: false,
    errorMessage: 'Probe timeout'
  };
}

export function buildIdentitySourceProbeRequest(input: {
  protocol: 'ldap' | 'ldaps' | string;
  host?: string | null;
  port?: number | null;
  baseDn?: string | null;
  bindDn?: string | null;
  secretRef?: string | null;
  authMode?: 'ntlm' | 'kerberos' | 'simple' | 'basic' | 'none';
  identitySourceId?: number | null;
  uiOrigin?: 'wizard' | 'admin';
}): ProbeRunRequest {
  const protocol = String(input.protocol ?? 'ldaps').toLowerCase() === 'ldap' ? 'ldap' : 'ldaps';
  const authMode = input.authMode ?? 'ntlm';

  const request: ProbeRunRequest = {
    kind: 'identity-source',
    protocol,
    scope: 'read',
    target: {
      host: input.host ?? undefined,
      port: input.port ?? undefined,
      base_dn: input.baseDn ?? undefined
    },
    options: {
      timeout_sec: 10,
      verify_tls: protocol === 'ldaps'
    },
    context: {
      identity_source_id: input.identitySourceId ?? undefined,
      ui_origin: input.uiOrigin ?? 'admin'
    }
  };

  if (input.bindDn || input.secretRef) {
    request.auth = {
      mode: authMode,
      username: input.bindDn ?? undefined,
      secret_ref: input.secretRef ?? undefined
    };
  }

  return request;
}

export function buildStorageEndpointProbeRequest(input: {
  protocol: 'smb' | string;
  host: string;
  port?: number | null;
  endpointId: number;
  username: string;
  domain?: string | null;
  secretRef?: string | null;
  password?: string | null;
  discover?: boolean;
  timeoutSec?: number;
  uiOrigin?: 'wizard' | 'admin';
}): ProbeRunRequest {
  return {
    kind: 'storage-endpoint',
    protocol: String(input.protocol ?? 'smb').toLowerCase() as any,
    scope: 'read',
    target: {
      host: input.host,
      port: input.port ?? undefined,
      storage_endpoint_id: input.endpointId
    },
    auth: {
      mode: 'ntlm',
      username: input.username,
      domain: input.domain ?? undefined,
      secret_ref: input.secretRef ?? undefined,
      password: input.secretRef ? undefined : (input.password ?? undefined)
    },
    options: {
      timeout_sec: Math.max(1, Math.min(Number(input.timeoutSec ?? 20), 30)),
      discover: input.discover ?? true
    },
    context: {
      ui_origin: input.uiOrigin ?? 'admin',
      storage_endpoint_id: input.endpointId
    }
  };
}

export type StorageRootAvailabilityRow = {
  storage_root_id: number;
  storage_root_name: string;
  root_path: string;
  provisioning_status: string;
  endpoint_status: string;
  available: boolean;
};

export type StorageRootAvailabilitySummary = {
  total: number;
  available: number;
  unavailable: number;
  rows: StorageRootAvailabilityRow[];
};

export type StorageRootDiscoverySyncItem = {
  root_path: string;
  permissions: Record<string, any>[];
};

export type StorageRootDiscoverySyncPayload = {
  storage_endpoint_id: number;
  discovered_at?: string;
  discovery_complete?: boolean;
  roots: StorageRootDiscoverySyncItem[];
};

export type StorageRootDiscoverySyncResponse = {
  ok: boolean;
  storage_endpoint_id: number;
  updated: number;
  marked_unreachable: number;
  unmatched_roots: string[];
};

const isProvisioningReadyLike = (value: unknown): boolean => {
  const key = String(value ?? '').trim().toLowerCase();
  return key === 'ready' || key === 'success';
};

const isEndpointProbeAvailable = (value: unknown): boolean =>
  normalizeProbeStatus(String(value ?? '')) === 'success';

const asObject = (value: unknown): Record<string, any> =>
  value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, any>)
    : {};

function parseDiscoveryPayloadFromProbeResult(result: any): {
  discoveredAt?: string;
  discoveryComplete: boolean;
  roots: StorageRootDiscoverySyncItem[];
} {
  const top = asObject(result);
  const details = asObject(top?.details);

  const discoveredAt = String(top?.discovered_at ?? details?.discovered_at ?? '').trim() || undefined;

  const rawRoots = Array.isArray(top?.roots)
    ? top.roots
    : Array.isArray(details?.roots)
      ? details.roots
      : [];

  const permissionsByRoot = asObject(top?.permissions_by_root);
  const detailsPermissionsByRoot = asObject(details?.permissions_by_root);

  const roots = rawRoots
    .map((raw) => String(raw ?? '').trim())
    .filter(Boolean)
    .map((rootPath) => {
      const permissions = Array.isArray(permissionsByRoot[rootPath])
        ? permissionsByRoot[rootPath]
        : Array.isArray(detailsPermissionsByRoot[rootPath])
          ? detailsPermissionsByRoot[rootPath]
          : [];
      return {
        root_path: rootPath,
        permissions
      } as StorageRootDiscoverySyncItem;
    });

  return {
    discoveredAt,
    discoveryComplete: details?.discovery_complete !== false,
    roots
  };
}

export async function syncStorageRootDiscoveryForEndpoint(
  fetchFn: FetchLike,
  endpointId: number,
  probeResult: any
): Promise<StorageRootDiscoverySyncResponse | null> {
  const normalizedEndpointId = Number(endpointId ?? 0);
  if (!Number.isFinite(normalizedEndpointId) || normalizedEndpointId <= 0) {
    return null;
  }

  const parsed = parseDiscoveryPayloadFromProbeResult(probeResult);
  const payload: StorageRootDiscoverySyncPayload = {
    storage_endpoint_id: normalizedEndpointId,
    discovery_complete: parsed.discoveryComplete,
    roots: parsed.roots
  };

  if (parsed.discoveredAt) {
    payload.discovered_at = parsed.discoveredAt;
  }

  return await apiPost<StorageRootDiscoverySyncResponse>(
    fetchFn,
    '/storage-roots/discovery-sync',
    payload
  );
}

export async function collectStorageRootsAvailabilityByEndpoint(
  fetchFn: FetchLike,
  endpointId: number
): Promise<StorageRootAvailabilitySummary> {
  const contextRows = await apiGetList<any>(fetchFn, '/storage-roots/context');
  const roots = (Array.isArray(contextRows) ? contextRows : [])
    .filter((r: any) => Number(r?.storage_endpoint_id ?? 0) === endpointId)
    .map((r: any) => ({
      storage_root_id: Number(r?.id ?? r?.storage_root_id ?? 0),
      storage_root_name: String(r?.name ?? r?.storage_root_name ?? 'Storage root'),
      root_path: String(r?.root_path ?? '')
    }))
    .filter((r) => r.storage_root_id > 0);

  const rows: StorageRootAvailabilityRow[] = await Promise.all(
    roots.map(async (root) => {
      try {
        const data: any = await apiGetData(fetchFn, `/storage-roots/${root.storage_root_id}/overview`);
        const provisioningStatus = String(
          data?.provisioning_status ??
            data?.governance?.provisioning_status ??
            'unknown'
        );
        const endpointStatus = String(
          data?.storage_endpoint?.last_probe_status ??
            data?.storage_endpoint_last_probe_status ??
            'unknown'
        );
        const endpointAvailable = isEndpointProbeAvailable(endpointStatus);
        const available = isProvisioningReadyLike(provisioningStatus) && endpointAvailable;

        return {
          storage_root_id: root.storage_root_id,
          storage_root_name: root.storage_root_name,
          root_path: root.root_path,
          provisioning_status: provisioningStatus,
          endpoint_status: endpointStatus,
          available
        };
      } catch {
        return {
          storage_root_id: root.storage_root_id,
          storage_root_name: root.storage_root_name,
          root_path: root.root_path,
          provisioning_status: 'unknown',
          endpoint_status: 'unknown',
          available: false
        };
      }
    })
  );

  const available = rows.filter((r) => r.available).length;
  const total = rows.length;
  return {
    total,
    available,
    unavailable: Math.max(0, total - available),
    rows
  };
}

export async function runCapsuleProbe<TPost = unknown>(
  options: RunCapsuleProbeOptions<TPost>
): Promise<RunCapsuleProbeSuccess<TPost> | RunCapsuleProbeFailure> {
  const { fetchFn, request } = options;
  try {
    logProbeStart(request);
    pushUiActivityLog('info', `Probe started: ${request.kind}/${request.protocol}`, { request });
    const res = await runProbeWithPolling<TPost>({
      fetchFn,
      request,
      intervalMs: options.intervalMs,
      maxAttempts: options.maxAttempts,
      onUpdate: options.onUpdate,
      afterSuccess: options.afterSuccess
    });

    logProbeResult(request, res);

    pushUiActivityLog(res.ok ? 'info' : 'error', `Probe ${res.ok ? 'OK' : 'FAILED'}: ${request.kind}/${request.protocol}`, { request, res });

    if (!res.ok) {
      return {
        ok: false,
        error: normalizeProbeError({ message: res.errorMessage ?? 'Probe failed' }),
        result: res
      };
    }
    return { ok: true, result: res };
  } catch (e: unknown) {
    const err = normalizeProbeError(e);
    logProbeResult(request, { status: 'failed', ok: false, errorMessage: err.message });
    pushUiActivityLog('error', `Probe error: ${request.kind}/${request.protocol}`, { request, error: err });
    return { ok: false, error: err };
  }
}
