import type { ProbeRunRequest } from '$lib/api/probes';
import {
  buildIdentitySourceProbeRequest,
  buildStorageEndpointProbeRequest
} from './probe-runner';

export { buildIdentitySourceProbeRequest, buildStorageEndpointProbeRequest };

/**
 * Optional generic ACL/StorageRoot probe builder.
 * Aligns with backend ProbeKind 'acl' and protocol 'acl_push'.
 */
export function buildAclProbeRequest(input: {
  zoneId?: number | null;
  storageEndpointId?: number | null;
  storageRootName?: string | null;
  dryRun?: boolean;
  uiOrigin?: 'wizard' | 'admin';
  target: Record<string, any>;
}): ProbeRunRequest {
  return {
    kind: 'acl',
    protocol: 'acl_push',
    scope: 'write',
    target: input.target,
    options: {
      dry_run: input.dryRun ?? true,
      timeout_sec: 20
    },
    context: {
      zone_id: input.zoneId ?? undefined,
      storage_endpoint_id: input.storageEndpointId ?? undefined,
      storage_root_name: input.storageRootName ?? undefined,
      ui_origin: input.uiOrigin ?? 'admin'
    }
  };
}


export function buildStorageEndpointConnectProbeRequest(input: {
  protocol?: 'smb' | string;
  host: string;
  port?: number | null;
  username?: string | null;
  domain?: string | null;
  secretRef?: string | null;
  password?: string | null;
  discover?: boolean;
  timeoutSec?: number;
  uiOrigin?: 'wizard' | 'admin';
}): ProbeRunRequest {
  return {
    kind: 'storage-endpoint',
    protocol: 'smb',
    scope: 'read',
    target: {
      host: input.host,
      port: input.port ?? undefined
    },
    auth: {
      mode: 'ntlm',
      username: input.username ?? undefined,
      domain: input.domain ?? undefined,
      secret_ref: input.secretRef ?? undefined,
      password: input.secretRef ? undefined : (input.password ?? undefined)
    },
    options: {
      timeout_sec: input.timeoutSec ?? 20,
      discover: input.discover ?? true
    },
    context: {
      ui_origin: input.uiOrigin ?? 'wizard'
    }
  };
}
