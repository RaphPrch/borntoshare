import { type StatusVariant } from '$lib/utils/status';

const asKey = (value: unknown): string =>
  String(value ?? '')
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, '_');

const PROBE_SUCCESS = new Set([
  'success',
  'succeeded',
  'ok',
  'passed'
]);

const PROBE_RUNNING = new Set([
  'queued',
  'running',
  'retrying',
  'pending'
]);

const PROBE_FAILED = new Set([
  'failed',
  'error',
  'timed_out',
  'timeout',
  'cancelled',
  'canceled'
]);

type NormalizedProbeStatus = 'success' | 'running' | 'failed' | 'unknown';

export function normalizeProbeStatus(status?: string | null): NormalizedProbeStatus {
  const key = asKey(status);
  if (!key) return 'unknown';
  if (PROBE_SUCCESS.has(key)) return 'success';
  if (PROBE_RUNNING.has(key)) return 'running';
  if (PROBE_FAILED.has(key)) return 'failed';
  return 'unknown';
}

type BindingIntegrity =
  | 'materialized'
  | 'pending_materialization'
  | 'missing'
  | 'ambiguous'
  | 'unknown';

function normalizeBindingIntegrity(input: {
  bindingStatus?: string | null;
  syntheticStatus?: string | null;
}): BindingIntegrity {
  const binding = asKey(input.bindingStatus);
  const synthetic = asKey(input.syntheticStatus);

  if (binding === 'materialized') return 'materialized';
  if (binding === 'inherited_candidate') return 'pending_materialization';
  if (binding === 'missing') return 'missing';
  if (binding === 'ambiguous') return 'ambiguous';

  if (synthetic === 'pending_materialization') return 'pending_materialization';
  if (synthetic === 'binding_missing') return 'missing';
  if (synthetic === 'ambiguous_binding') return 'ambiguous';

  return 'unknown';
}

type ReachabilityState = 'reachable' | 'checking' | 'unreachable' | 'unknown';

export function reachabilityFromProbeStatus(status: NormalizedProbeStatus): ReachabilityState {
  if (status === 'success') return 'reachable';
  if (status === 'running') return 'checking';
  if (status === 'failed') return 'unreachable';
  return 'unknown';
}

type RootAccessProfileAttachment = 'attached' | 'missing';
type RootOwnershipState = 'ok' | 'missing';
type RootOverallState = 'healthy' | 'attention' | 'critical' | 'unknown';

type RootBusinessState = {
  endpointReachability: ReachabilityState;
  accessProfileAttachment: RootAccessProfileAttachment;
  bindingIntegrity: BindingIntegrity;
  ownership: RootOwnershipState;
  overall: RootOverallState;
};

export function deriveRootBusinessState(input: {
  runtimeProbeStatus?: string | null;
  persistedProbeStatus?: string | null;
  hasAttachedProfiles?: boolean | null;
  bindingStatus?: string | null;
  syntheticStatus?: string | null;
  hasOwners?: boolean | null;
}): RootBusinessState {
  const runtimeProbe = normalizeProbeStatus(input.runtimeProbeStatus);
  const persistedProbe = normalizeProbeStatus(input.persistedProbeStatus);
  const effectiveProbe = runtimeProbe === 'unknown' ? persistedProbe : runtimeProbe;

  const endpointReachability = reachabilityFromProbeStatus(effectiveProbe);
  const accessProfileAttachment: RootAccessProfileAttachment = input.hasAttachedProfiles ? 'attached' : 'missing';
  const bindingIntegrity = normalizeBindingIntegrity({
    bindingStatus: input.bindingStatus,
    syntheticStatus: input.syntheticStatus
  });
  const ownership: RootOwnershipState = input.hasOwners === false ? 'missing' : 'ok';

  if (endpointReachability === 'unreachable') {
    return { endpointReachability, accessProfileAttachment, bindingIntegrity, ownership, overall: 'critical' };
  }
  if (bindingIntegrity === 'missing' || bindingIntegrity === 'ambiguous') {
    return { endpointReachability, accessProfileAttachment, bindingIntegrity, ownership, overall: 'critical' };
  }
  if (
    endpointReachability === 'checking' ||
    bindingIntegrity === 'pending_materialization' ||
    accessProfileAttachment === 'missing' ||
    ownership === 'missing'
  ) {
    return { endpointReachability, accessProfileAttachment, bindingIntegrity, ownership, overall: 'attention' };
  }
  if (
    endpointReachability === 'reachable' &&
    accessProfileAttachment === 'attached' &&
    bindingIntegrity === 'materialized'
  ) {
    return { endpointReachability, accessProfileAttachment, bindingIntegrity, ownership, overall: 'healthy' };
  }
  if (endpointReachability === 'unknown' && bindingIntegrity === 'unknown') {
    return { endpointReachability, accessProfileAttachment, bindingIntegrity, ownership, overall: 'unknown' };
  }

  return { endpointReachability, accessProfileAttachment, bindingIntegrity, ownership, overall: 'attention' };
}

type IdentitySourceHealth = 'healthy' | 'checking' | 'degraded' | 'issue' | 'disabled' | 'unknown';
type IdentitySnapshotHealth = 'fresh' | 'running' | 'stale' | 'failed' | 'never' | 'na' | 'unknown';
type IdentityOverallState = 'healthy' | 'attention' | 'critical' | 'disabled' | 'unknown';

type IdentitySourceBusinessState = {
  sourceHealth: IdentitySourceHealth;
  snapshotHealth: IdentitySnapshotHealth;
  overall: IdentityOverallState;
};

function normalizeIdentitySourceHealth(input: {
  status?: string | null;
  isEnabled?: boolean | null;
  probeJobStatus?: string | null;
}): IdentitySourceHealth {
  if (input.isEnabled === false) return 'disabled';

  const job = asKey(input.probeJobStatus);
  if (job === 'running') return 'checking';

  const key = asKey(input.status);
  if (!key) return 'unknown';
  if (PROBE_SUCCESS.has(key)) return 'healthy';
  if (PROBE_RUNNING.has(key)) return 'checking';
  if (['warning', 'stale', 'degraded'].includes(key)) return 'degraded';
  if (PROBE_FAILED.has(key)) return 'issue';

  return 'unknown';
}

function normalizeIdentitySnapshotHealth(input: {
  status?: string | null;
  lastSnapshotAt?: string | null;
  snapshotJobStatus?: string | null;
  supportsSnapshot?: boolean | null;
}): IdentitySnapshotHealth {
  if (input.supportsSnapshot === false) return 'na';

  const job = asKey(input.snapshotJobStatus);
  if (job === 'running') return 'running';
  if (job === 'error' || job === 'failed') return 'failed';

  const key = asKey(input.status);
  const hasSnapshotDate = Boolean(String(input.lastSnapshotAt ?? '').trim());

  if (!key && !hasSnapshotDate) return 'never';
  if (['success', 'succeeded', 'active', 'synced', 'up_to_date'].includes(key)) return 'fresh';
  if (PROBE_RUNNING.has(key)) return 'running';
  if (['warning', 'stale', 'needs_refresh', 'partial'].includes(key)) return 'stale';
  if (PROBE_FAILED.has(key) || key === 'cancelled' || key === 'canceled') return 'failed';
  if (!key && hasSnapshotDate) return 'fresh';

  return 'unknown';
}

export function deriveIdentitySourceBusinessState(input: {
  status?: string | null;
  isEnabled?: boolean | null;
  probeJobStatus?: string | null;
  snapshotStatus?: string | null;
  snapshotJobStatus?: string | null;
  lastSnapshotAt?: string | null;
  supportsSnapshot?: boolean | null;
}): IdentitySourceBusinessState {
  const sourceHealth = normalizeIdentitySourceHealth({
    status: input.status,
    isEnabled: input.isEnabled,
    probeJobStatus: input.probeJobStatus
  });
  const snapshotHealth = normalizeIdentitySnapshotHealth({
    status: input.snapshotStatus,
    snapshotJobStatus: input.snapshotJobStatus,
    lastSnapshotAt: input.lastSnapshotAt,
    supportsSnapshot: input.supportsSnapshot
  });

  if (sourceHealth === 'disabled') {
    return { sourceHealth, snapshotHealth, overall: 'disabled' };
  }
  if (sourceHealth === 'issue' || snapshotHealth === 'failed') {
    return { sourceHealth, snapshotHealth, overall: 'critical' };
  }
  if (
    sourceHealth === 'checking' ||
    sourceHealth === 'degraded' ||
    snapshotHealth === 'running' ||
    snapshotHealth === 'stale' ||
    snapshotHealth === 'never'
  ) {
    return { sourceHealth, snapshotHealth, overall: 'attention' };
  }
  if (sourceHealth === 'healthy' && (snapshotHealth === 'fresh' || snapshotHealth === 'na')) {
    return { sourceHealth, snapshotHealth, overall: 'healthy' };
  }

  return { sourceHealth, snapshotHealth, overall: 'unknown' };
}

type RequestWorkflowState = 'pending' | 'approved' | 'enforced' | 'revoked' | 'rejected' | 'unknown';
type RequestProvisioningState = 'running' | 'queued' | 'success' | 'failed' | 'unknown';
type AccessRequestOverallState = 'pending' | 'success' | 'error' | 'unknown';

function normalizeRequestWorkflowState(status?: string | null): RequestWorkflowState {
  const key = asKey(status);
  if (!key) return 'unknown';
  if (key === 'pending') return 'pending';
  if (key === 'approved') return 'approved';
  if (key === 'enforced') return 'enforced';
  if (key === 'revoked') return 'revoked';
  if (key === 'rejected') return 'rejected';
  if (key.includes('success') || key.includes('approved') || key.includes('applied')) return 'approved';
  if (key.includes('reject') || key.includes('deny') || key.includes('error') || key.includes('fail')) {
    return 'rejected';
  }
  return 'unknown';
}

function normalizeRequestProvisioningState(status?: string | null): RequestProvisioningState {
  const key = asKey(status);
  if (!key) return 'unknown';
  if (key === 'running') return 'running';
  if (key === 'queued') return 'queued';
  if (key === 'success' || key === 'succeeded') return 'success';
  if (key === 'failed' || key === 'error') return 'failed';
  return 'unknown';
}

export function deriveAccessRequestBusinessState(input: {
  workflowStatus?: string | null;
  provisioningStatus?: string | null;
}): {
  workflow: RequestWorkflowState;
  provisioning: RequestProvisioningState;
  overall: AccessRequestOverallState;
} {
  const workflow = normalizeRequestWorkflowState(input.workflowStatus);
  const provisioning = normalizeRequestProvisioningState(input.provisioningStatus);

  if (workflow === 'unknown' && provisioning === 'unknown') {
    return { workflow, provisioning, overall: 'unknown' };
  }
  if (workflow === 'rejected' || provisioning === 'failed') {
    return { workflow, provisioning, overall: 'error' };
  }
  if (workflow === 'pending' || provisioning === 'running' || provisioning === 'queued') {
    return { workflow, provisioning, overall: 'pending' };
  }
  return { workflow, provisioning, overall: 'success' };
}

export function mapAccessRequestOverallToVariant(overall: AccessRequestOverallState): StatusVariant {
  if (overall === 'success') return 'success';
  if (overall === 'pending') return 'warning';
  if (overall === 'error') return 'error';
  return 'muted';
}
