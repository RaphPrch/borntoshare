import { writable } from 'svelte/store';
import type { ProbeRunRequest } from '$lib/api/probes';

export type ProbeLogEntry = {
  id: string;
  timestamp: number;
  kind: string;
  protocol?: string;
  scope?: string;
  status: string;
  ok?: boolean;
  job_id?: string;
  message?: string;
  details?: any;
};

export const probeLogs = writable<ProbeLogEntry[]>([]);

const uuid = () => {
  try {
    return crypto.randomUUID();
  } catch {
    return String(Date.now()) + '-' + String(Math.random()).slice(2);
  }
};

export function pushProbeLog(entry: Omit<ProbeLogEntry, 'id' | 'timestamp'>) {
  probeLogs.update((logs) => [
    { id: uuid(), timestamp: Date.now(), ...entry },
    ...logs
  ].slice(0, 200));
}

export function logProbeStart(request: ProbeRunRequest) {
  pushProbeLog({
    kind: request.kind,
    protocol: request.protocol,
    scope: request.scope,
    status: 'running',
    ok: undefined,
    details: { target: request.target, context: request.context }
  });
}

export function logProbeResult(
  request: ProbeRunRequest,
  result: { jobId?: string; status: string; ok: boolean; errorMessage?: string; result?: any }
) {
  pushProbeLog({
    kind: request.kind,
    protocol: request.protocol,
    scope: request.scope,
    status: result.status,
    ok: result.ok,
    job_id: result.jobId,
    message: result.ok ? 'OK' : (result.errorMessage ?? 'Failed'),
    details: result.result
  });
}
