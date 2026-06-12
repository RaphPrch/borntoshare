export type OperationalHeaderTone = 'success' | 'warning' | 'danger' | 'neutral' | 'info';

export type ZoneOperationalAttentionInput = {
  endpointCount: number;
  reachableCount: number;
  nonRunnableCount: number;
  provisioningReady: boolean;
  healthLabel?: 'ok' | 'warning';
};

export type StorageEndpointOperationalAttentionInput = {
  healthLabel: string;
  healthDetail?: string | null;
  hostReady: boolean;
  hostLabel?: string | null;
  pendingRequestCount: number;
  provisioningWarnings?: string[];
};

export const healthLabelToOperationalTone = (healthLabel: 'ok' | 'warning'): OperationalHeaderTone =>
  healthLabel === 'ok' ? 'success' : 'warning';

export const endpointHealthToOperationalTone = (health: string): OperationalHeaderTone => {
  const normalized = String(health ?? '').trim().toLowerCase();
  if (normalized === 'healthy' || normalized === 'reachable' || normalized === 'success') return 'success';
  if (normalized === 'degraded' || normalized === 'checking' || normalized === 'running') return 'warning';
  return 'danger';
};

export const visualToneToOperationalTone = (tone: string): OperationalHeaderTone => {
  const normalized = String(tone ?? '').trim().toLowerCase();
  if (normalized === 'success' || normalized === 'healthy' || normalized === 'reachable' || normalized === 'ok') {
    return 'success';
  }
  if (
    normalized === 'danger' ||
    normalized === 'error' ||
    normalized === 'failed' ||
    normalized === 'unhealthy' ||
    normalized === 'unreachable'
  ) {
    return 'danger';
  }
  if (normalized === 'info') return 'info';
  if (normalized === 'neutral') return 'neutral';
  return 'warning';
};

export function buildZoneOperationalAttentionItems(input: ZoneOperationalAttentionInput): string[] {
  const endpointCount = Math.max(0, Number(input.endpointCount ?? 0));
  const reachableCount = Math.max(0, Number(input.reachableCount ?? 0));
  const nonRunnableCount = Math.max(0, Number(input.nonRunnableCount ?? 0));
  const unhealthyCount = Math.max(0, endpointCount - reachableCount);

  const items = [
    endpointCount === 0
      ? 'No storage endpoint attached to this zone yet.'
      : reachableCount === 0
        ? 'No endpoint is currently reachable in this zone.'
        : unhealthyCount > 0
          ? `${unhealthyCount} endpoint${unhealthyCount > 1 ? 's are' : ' is'} not reachable.`
          : null,
    nonRunnableCount > 0
      ? `${nonRunnableCount} endpoint${nonRunnableCount > 1 ? 's are' : ' is'} missing host and/or credentials.`
      : null,
    input.provisioningReady ? null : 'Provisioning policy is incomplete.'
  ].filter(Boolean) as string[];

  if (items.length === 0 && input.healthLabel === 'warning') {
    items.push('Zone configuration needs review.');
  }

  return [...new Set(items)];
}

export function buildStorageEndpointOperationalAttentionItems(
  input: StorageEndpointOperationalAttentionInput
): string[] {
  const healthLabel = String(input.healthLabel ?? '').trim();
  const healthDetail = String(input.healthDetail ?? '').trim();
  const hostLabel = String(input.hostLabel ?? '').trim();
  const pendingRequestCount = Math.max(0, Number(input.pendingRequestCount ?? 0));
  const provisioningWarnings = (input.provisioningWarnings ?? [])
    .map((message) => String(message ?? '').trim())
    .filter(Boolean);

  const items = [
    healthLabel.toLowerCase() === 'reachable'
      ? null
      : healthLabel.toLowerCase() === 'unreachable'
        ? 'Endpoint is currently unreachable.'
      : `${healthLabel || 'Endpoint status unknown'}${healthDetail ? `: ${healthDetail}` : '.'}`,
    input.hostReady ? null : `Endpoint host is missing${hostLabel ? `: ${hostLabel}` : '.'}`,
    pendingRequestCount > 0
      ? `${pendingRequestCount} access request${pendingRequestCount > 1 ? 's are' : ' is'} waiting for review.`
      : null,
    ...provisioningWarnings
  ].filter(Boolean) as string[];

  return [...new Set(items)];
}
