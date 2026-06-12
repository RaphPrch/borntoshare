import { normalizeProbeStatus, reachabilityFromProbeStatus } from '../services/mappers/visual-state.mapper';

const normalizeRuntimeProbeStatus = (status?: string | null): 'running' | 'success' | 'failed' | null => {
  const key = String(status ?? '').trim().toLowerCase();
  if (key === 'running' || key === 'success' || key === 'failed') return key;
  return null;
};

export function effectiveRootProbeStatus(input: {
  runtimeStatus?: string | null;
  persistedStatus?: string | null;
}): string {
  const runtime = normalizeRuntimeProbeStatus(input.runtimeStatus);
  if (runtime) return runtime;
  return String(input.persistedStatus ?? '').trim().toLowerCase();
}

export function rootToneFromProbeStatus(input: {
  runtimeStatus?: string | null;
  persistedStatus?: string | null;
}): 'healthy' | 'warning' | 'error' {
  const effective = effectiveRootProbeStatus(input);
  const reachability = reachabilityFromProbeStatus(normalizeProbeStatus(effective));
  if (reachability === 'reachable') return 'healthy';
  if (reachability === 'unreachable') return 'error';
  return 'warning';
}
