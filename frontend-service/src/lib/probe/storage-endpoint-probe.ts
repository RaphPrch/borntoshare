import type { ProbeRunRequest } from '$lib/api/probes';
import { buildStorageEndpointProbeRequest } from './probe-runner';

export type StorageEndpointProbeInput = Record<string, any>;

export type StorageEndpointProbeConfig = {
  endpointId: number;
  protocol: string;
  host: string;
  port?: number | null;
  username: string;
  domain?: string | null;
  secretRef: string | null;
};

export type StorageEndpointProbeValidation = {
  ok: boolean;
  message?: string;
  config?: StorageEndpointProbeConfig;
};

export function endpointIdOfProbeTarget(endpoint: StorageEndpointProbeInput | null | undefined): number {
  return Number(endpoint?.storage_endpoint_id ?? endpoint?.id ?? 0);
}

export function endpointProtocolOfProbeTarget(endpoint: StorageEndpointProbeInput | null | undefined): string {
  return String(endpoint?.protocol ?? endpoint?.type ?? endpoint?.storage_endpoint_type ?? 'smb')
    .trim()
    .toLowerCase();
}

export function endpointUsernameOfProbeTarget(endpoint: StorageEndpointProbeInput | null | undefined): string {
  return String(
    endpoint?.auth_user ??
      endpoint?.auth_username ??
      endpoint?.username ??
      endpoint?.bind_dn ??
      endpoint?.user ??
      ''
  ).trim();
}

export function endpointSecretRefOfProbeTarget(endpoint: StorageEndpointProbeInput | null | undefined): string | null {
  const raw = String(endpoint?.auth_secret_ref ?? endpoint?.bind_password_ref ?? endpoint?.secret_ref ?? '').trim();
  return raw || null;
}

export function extractDomainFromUsername(username?: string | null): string | undefined {
  const value = String(username ?? '').trim();
  if (!value) return undefined;
  if (value.includes('\\')) return value.split('\\')[0]?.trim() || undefined;
  if (value.includes('/')) return value.split('/')[0]?.trim() || undefined;
  return undefined;
}

export function resolveStorageEndpointProbeConfig(
  endpoint: StorageEndpointProbeInput | null | undefined
): StorageEndpointProbeConfig {
  const endpointId = endpointIdOfProbeTarget(endpoint);
  const protocol = endpointProtocolOfProbeTarget(endpoint);
  const host = String(endpoint?.host ?? '').trim();
  const username = endpointUsernameOfProbeTarget(endpoint);
  const secretRef = endpointSecretRefOfProbeTarget(endpoint);

  return {
    endpointId,
    protocol,
    host,
    port: endpoint?.port ?? null,
    username,
    domain: extractDomainFromUsername(username),
    secretRef
  };
}

export function validateStorageEndpointProbeConfig(
  config: StorageEndpointProbeConfig,
  options?: {
    label?: string;
    requireSecret?: boolean;
  }
): StorageEndpointProbeValidation {
  const label = options?.label ?? 'Storage endpoint';
  const requireSecret = options?.requireSecret ?? true;

  if (!Number.isFinite(config.endpointId) || config.endpointId <= 0) {
    return { ok: false, message: `Invalid ${label.toLowerCase()} for probe run` };
  }
  if (config.protocol !== 'smb' && config.protocol !== 'cifs') {
    return { ok: false, message: `${label} probe is available only for SMB/CIFS` };
  }
  if (!config.host) {
    return { ok: false, message: `${label} host is missing` };
  }
  if (!config.username) {
    return { ok: false, message: `${label} username / bind_dn is missing` };
  }
  if (requireSecret && !config.secretRef) {
    return { ok: false, message: `${label} bind_password_ref is required for probe` };
  }
  return { ok: true, config };
}

export function buildStorageEndpointProbeRequestFromEndpoint(
  endpoint: StorageEndpointProbeInput | null | undefined,
  options?: {
    discover?: boolean;
    timeoutSec?: number;
    uiOrigin?: 'wizard' | 'admin';
    label?: string;
  }
): ProbeRunRequest {
  const config = resolveStorageEndpointProbeConfig(endpoint);
  const validation = validateStorageEndpointProbeConfig(config, { label: options?.label });
  if (!validation.ok) {
    throw new Error(validation.message ?? 'Invalid storage endpoint probe configuration');
  }

  return buildStorageEndpointProbeRequest({
    protocol: 'smb',
    host: config.host,
    port: config.port,
    endpointId: config.endpointId,
    username: config.username,
    domain: config.domain,
    secretRef: config.secretRef,
    discover: options?.discover ?? true,
    timeoutSec: options?.timeoutSec ?? 30,
    uiOrigin: options?.uiOrigin ?? 'admin'
  });
}

export function buildStorageRootProbeRequest(input: {
  storageRootId: number;
  storageEndpointId?: number | null;
  storageRootName?: string | null;
  timeoutSec?: number;
  uiOrigin?: 'wizard' | 'admin';
}): ProbeRunRequest {
  return {
    kind: 'storage-root',
    protocol: 'smb',
    scope: 'read',
    target: {
      storage_root_id: input.storageRootId
    },
    options: {
      timeout_sec: Math.max(1, Math.min(Number(input.timeoutSec ?? 20), 30)),
      discover_permissions: true
    },
    context: {
      storage_root_id: input.storageRootId,
      storage_endpoint_id: input.storageEndpointId ?? undefined,
      storage_root_name: input.storageRootName ?? undefined,
      ui_origin: input.uiOrigin ?? 'admin'
    }
  };
}

export function parseStorageEndpointProbeRoots(result: any): string[] {
  const candidates =
    result?.details?.roots ??
    result?.roots ??
    result?.discovered_roots ??
    result?.details?.shares ??
    [];

  if (!Array.isArray(candidates)) return [];
  const normalized = candidates.map((r: any) => String(r ?? '').trim()).filter(Boolean);
  return [...new Set(normalized)];
}
