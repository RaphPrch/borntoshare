import { getProbeJob, type ProbeJob } from '../../api/probes';
import type { FetchLike } from '../../api/client';
import { pollJobUntilTerminal } from './polling';
import type { JobPollingResult } from './types';

export async function pollProbeJob(
  fetchFn: FetchLike,
  jobId: string | number,
  options?: {
    intervalMs?: number;
    maxAttempts?: number;
    intervalMsByAttempt?: (attempt: number) => number;
  }
): Promise<JobPollingResult<any>> {
  return pollJobUntilTerminal(String(jobId), {
    fetchJob: (id: string) => getProbeJob(fetchFn, id),
    getRawStatus: (job: ProbeJob) => String(job?.status ?? ''),
    mapPayload: (job: ProbeJob) => job,
    getErrorMessage: (job: ProbeJob) => job?.error?.message,
    intervalMs: options?.intervalMs ?? 3000,
    maxAttempts: options?.maxAttempts,
    intervalMsByAttempt: options?.intervalMsByAttempt
  });
}
