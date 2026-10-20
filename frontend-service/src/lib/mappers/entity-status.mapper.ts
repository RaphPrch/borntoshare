import { t } from '$lib/i18n';
import type { StatusVariant } from '$lib/utils/status';
import {
  endpointOperationalStateLabel,
  endpointOperationalStateVariant
} from './endpoint-operational-state.mapper';
import {
  normalizeProbeStatus
} from './visual-state.mapper';
import {
  normalizeStorageRootAvailability,
  storageRootToneFromAvailability,
  type RootAvailability
} from './storage-root-detail.mapper';

export { endpointOperationalStateLabel, endpointOperationalStateVariant, normalizeProbeStatus, normalizeStorageRootAvailability };

export type { RootAvailability };

export function probeStatusLabel(value: unknown): string {
  const probe = normalizeProbeStatus(String(value ?? ''));
  if (probe === 'running') return t('Running');
  if (probe === 'success') return t('Success');
  if (probe === 'failed') return t('Failed');
  return t('Unknown');
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
  if (availability === 'reachable') return t('Reachable');
  if (availability === 'checking') return t('Checking');
  if (availability === 'unreachable') return t('Unreachable');
  if (availability === 'blocked_by_endpoint') return t('Endpoint blocked');
  if (availability === 'needs_revalidation') return t('Revalidation needed');
  if (availability === 'root_unreachable') return t('Root unreachable');
  if (availability === 'needs_root_probe') return t('Root probe needed');
  if (availability === 'not_provisioned') return t('Not provisioned');
  return t('Unknown');
}

export function rootAvailabilityVariant(value: unknown): StatusVariant {
  const tone = storageRootToneFromAvailability(normalizeStorageRootAvailability(value));
  if (tone === 'healthy') return 'success';
  if (tone === 'error') return 'error';
  return 'warning';
}
