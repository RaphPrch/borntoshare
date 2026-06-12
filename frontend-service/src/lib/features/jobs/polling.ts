import { isJobTerminal, normalizeJobStatus } from './status';
import type { JobPollingOptions, JobPollingResult } from './types';

export async function pollJobUntilTerminal<TRawJob = any, TPayload = any>(
  jobId: string,
  options: JobPollingOptions<TRawJob, TPayload>
): Promise<JobPollingResult<TPayload>> {
  const {
    fetchJob,
    getRawStatus,
    mapPayload,
    getErrorMessage,
    intervalMs = 1500,
    maxAttempts = 40,
    intervalMsByAttempt,
    onUpdate
  } = options;

  const normalizedJobId = String(jobId ?? '').trim();
  if (!normalizedJobId) {
    throw new Error('Missing job_id');
  }

  for (let attempt = 0; attempt <= maxAttempts; attempt++) {
    const rawJob = await fetchJob(normalizedJobId);
    const status = normalizeJobStatus(getRawStatus(rawJob));
    onUpdate?.(status, rawJob);

    if (isJobTerminal(status)) {
      return {
        jobId: normalizedJobId,
        status,
        payload: mapPayload ? mapPayload(rawJob) : undefined,
        errorMessage: getErrorMessage?.(rawJob)
      };
    }

    const waitMs = Math.max(
      0,
      Math.trunc(
        Number(
          typeof intervalMsByAttempt === 'function'
            ? intervalMsByAttempt(attempt)
            : intervalMs
        ) || intervalMs
      )
    );
    await new Promise((resolve) => setTimeout(resolve, waitMs));
  }

  return {
    jobId: normalizedJobId,
    status: 'timeout',
    errorMessage: 'Job polling timeout'
  };
}
