import type { ProbeRunRequest } from '$lib/api/probes';
import {
  buildIdentitySourceProbeRequest
} from './probe-runner';

export { buildIdentitySourceProbeRequest };

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
