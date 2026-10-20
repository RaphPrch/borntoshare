import { t } from '$lib/i18n';
import type { StatusVariant } from '$lib/utils/status';

type EndpointOperationalState =
  | 'reachable'
  | 'checking'
  | 'unreachable'
  | 'disabled'
  | 'unknown';

function normalizeEndpointOperationalState(value: unknown): EndpointOperationalState {
  const state = String(value ?? '').trim().toLowerCase();
  if (state === 'reachable') return 'reachable';
  if (state === 'checking') return 'checking';
  if (state === 'unreachable') return 'unreachable';
  if (state === 'disabled') return 'disabled';
  return 'unknown';
}

export function endpointOperationalStateLabel(value: unknown): string {
  const state = normalizeEndpointOperationalState(value);
  if (state === 'reachable') return t('Reachable');
  if (state === 'checking') return t('Checking');
  if (state === 'unreachable') return t('Unreachable');
  if (state === 'disabled') return t('Disabled');
  return t('Unknown');
}

export function endpointOperationalStateVariant(value: unknown): StatusVariant {
  const state = normalizeEndpointOperationalState(value);
  if (state === 'reachable') return 'success';
  if (state === 'checking') return 'info';
  if (state === 'unreachable') return 'error';
  if (state === 'disabled') return 'disabled';
  return 'muted';
}

