import type { JobUiStatus } from './types';

export function normalizeJobStatus(raw: string | null | undefined): JobUiStatus {
  const s = String(raw ?? '').toLowerCase().trim();
  if (!s) return 'never_run';
  if (s === 'queued') return 'queued';
  if (s === 'running' || s === 'retrying') return 'running';
  if (s === 'success' || s === 'succeeded') return 'success';
  if (s === 'timeout' || s === 'timed_out') return 'timeout';
  if (s === 'failed' || s === 'error' || s === 'cancelled' || s === 'canceled') return 'error';
  return 'error';
}

export function isJobTerminal(status: JobUiStatus): boolean {
  return status === 'success' || status === 'error' || status === 'timeout';
}
