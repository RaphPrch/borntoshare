import type { StatusVariant } from '$lib/constants/status';
import {
  endpointOperationalStateLabel,
  endpointOperationalStateVariant,
  normalizeEndpointOperationalState,
  type EndpointOperationalState
} from './endpoint-operational-state.mapper';
import {
  normalizeProbeStatus,
  type NormalizedProbeStatus
} from './visual-state.mapper';
import {
  normalizeStorageRootAvailability,
  storageRootToneFromAvailability,
  type RootAvailability,
  type RootTone
} from './storage-root-detail.mapper';

export {
  endpointOperationalStateLabel,
  endpointOperationalStateVariant,
  normalizeEndpointOperationalState,
  normalizeProbeStatus,
  normalizeStorageRootAvailability,
  storageRootToneFromAvailability
};

export type {
  EndpointOperationalState,
  NormalizedProbeStatus,
  RootAvailability,
  RootTone
};

export function probeStatusLabel(value: unknown): string {
  const probe = normalizeProbeStatus(String(value ?? ''));
  if (probe === 'running') return 'Running';
  if (probe === 'success') return 'Success';
  if (probe === 'failed') return 'Failed';
  return 'Unknown';
}

export function probeStatusVariant(value: unknown): StatusVariant {
  const probe = normalizeProbeStatus(String(value ?? ''));
  if (probe === 'running') return 'info';
  if (probe === 'success') return 'success';
  if (probe === 'failed') return 'error';
  return 'muted';
}

export function rootAvailabilityLabel(value: unknown): string {
  const availability = normalizeStorageRootAvailability(value);
  if (availability === 'reachable') return 'Reachable';
  if (availability === 'checking') return 'Checking';
  if (availability === 'unreachable') return 'Unreachable';
  if (availability === 'blocked_by_endpoint') return 'Endpoint blocked';
  if (availability === 'needs_revalidation') return 'Revalidation needed';
  if (availability === 'root_unreachable') return 'Root unreachable';
  if (availability === 'needs_root_probe') return 'Root probe needed';
  if (availability === 'not_provisioned') return 'Not provisioned';
  return 'Unknown';
}

export function rootAvailabilityVariant(value: unknown): StatusVariant {
  const tone = storageRootToneFromAvailability(normalizeStorageRootAvailability(value));
  if (tone === 'healthy') return 'success';
  if (tone === 'error') return 'error';
  return 'warning';
}
