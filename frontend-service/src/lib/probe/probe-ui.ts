import type { FetchLike } from '../api/client';
import type { ProbeRunRequest } from '../api/probes';
import type { ProbeSnapshot } from './probe-runner';
import { runProbeWithPolling } from './probe-runner';

type Notify = {
  success: (message: string) => void;
  error: (message: string) => void;
};

export function updateProbeJobsMap(
  current: Record<string, { status: string; ok?: boolean }>,
  key: string | number,
  snapshot: ProbeSnapshot
) {
  return {
    ...current,
    [String(key)]: {
      status: snapshot.status,
      ok: snapshot.ok
    }
  };
}

export function markProbeFailed(
  current: Record<string, { status: string; ok?: boolean }>,
  key: string | number
) {
  return {
    ...current,
    [String(key)]: {
      status: 'failed',
      ok: false
    }
  };
}

export async function runProbeWithUi<TPost = unknown>(input: {
  fetchFn: FetchLike;
  request: ProbeRunRequest;
  intervalMs?: number;
  maxAttempts?: number;
  onUpdate?: (snapshot: ProbeSnapshot) => void;
  afterSuccess?: (result: any) => Promise<TPost>;
  notify?: Notify;
  successMessage?: string | ((result: { postCheck?: TPost }) => string);
  failureMessage?: string | ((result: { errorMessage?: string }) => string);
}) {
  const {
    fetchFn,
    request,
    intervalMs,
    maxAttempts,
    onUpdate,
    afterSuccess,
    notify,
    successMessage,
    failureMessage
  } = input;

  const final = await runProbeWithPolling<TPost>({
    fetchFn,
    request,
    intervalMs,
    maxAttempts,
    onUpdate,
    afterSuccess
  });

  if (final.ok) {
    if (notify) {
      const message =
        typeof successMessage === 'function'
          ? successMessage({ postCheck: final.postCheck })
          : successMessage ?? 'Probe OK.';
      notify.success(message);
    }
    return final;
  }

  if (notify) {
    const message =
      typeof failureMessage === 'function'
        ? failureMessage({ errorMessage: final.errorMessage })
        : failureMessage ?? final.errorMessage ?? 'Probe failed.';
    notify.error(message);
  }

  return final;
}
