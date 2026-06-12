import { get, writable } from 'svelte/store';

export type JobStatus = 'idle' | 'running' | 'success' | 'error';

export type JobKeyInput = {
  entityType: string;
  entityId: string | number;
  action: string;
};

export type UiJob = JobKeyInput & {
  key: string;
  status: JobStatus;
  ok?: boolean;
  message?: string | null;
  error?: string | null;
  summary?: unknown;
  payload?: unknown;
  startedAt?: string | null;
  finishedAt?: string | null;
  updatedAt: string;
};

export type JobsState = Record<string, UiJob>;

const nowIso = () => new Date().toISOString();

const keyOf = ({ entityType, entityId, action }: JobKeyInput): string =>
  `${String(entityType)}::${String(entityId)}::${String(action)}`;

function createJobsStore() {
  const { subscribe, update, set } = writable<JobsState>({});

  const upsertJob = (
    input: JobKeyInput,
    patch: Partial<Omit<UiJob, 'key' | 'entityType' | 'entityId' | 'action'>> = {}
  ) => {
    const key = keyOf(input);
    const timestamp = nowIso();
    update((state) => {
      const previous = state[key];
      const next: UiJob = {
        key,
        entityType: input.entityType,
        entityId: input.entityId,
        action: input.action,
        status: patch.status ?? previous?.status ?? 'idle',
        ok: patch.ok ?? previous?.ok,
        message: patch.message ?? previous?.message ?? null,
        error: patch.error ?? previous?.error ?? null,
        summary: patch.summary ?? previous?.summary,
        payload: patch.payload ?? previous?.payload,
        startedAt: patch.startedAt ?? previous?.startedAt ?? null,
        finishedAt: patch.finishedAt ?? previous?.finishedAt ?? null,
        updatedAt: timestamp
      };
      return {
        ...state,
        [key]: next
      };
    });
    return key;
  };

  const startJob = (
    input: JobKeyInput,
    options?: { message?: string | null; payload?: unknown }
  ) =>
    upsertJob(input, {
      status: 'running',
      ok: undefined,
      error: null,
      message: options?.message ?? null,
      payload: options?.payload,
      summary: undefined,
      startedAt: nowIso(),
      finishedAt: null
    });

  const succeedJob = (
    input: JobKeyInput,
    options?: { message?: string | null; summary?: unknown; payload?: unknown }
  ) =>
    upsertJob(input, {
      status: 'success',
      ok: true,
      error: null,
      message: options?.message ?? null,
      summary: options?.summary,
      payload: options?.payload,
      finishedAt: nowIso()
    });

  const failJob = (
    input: JobKeyInput,
    options?: { error?: string | null; message?: string | null; payload?: unknown }
  ) =>
    upsertJob(input, {
      status: 'error',
      ok: false,
      error: options?.error ?? options?.message ?? 'Unknown error',
      message: options?.message ?? null,
      payload: options?.payload,
      finishedAt: nowIso()
    });

  const clearJob = (input: JobKeyInput) => {
    const key = keyOf(input);
    update((state) => {
      const next = { ...state };
      delete next[key];
      return next;
    });
  };

  const clearEntityJobs = (entityType: string, entityId?: string | number) => {
    update((state) => {
      const next = { ...state };
      for (const [key, job] of Object.entries(state)) {
        const sameType = job.entityType === entityType;
        const sameId =
          entityId === undefined ? true : String(job.entityId) === String(entityId);
        if (sameType && sameId) {
          delete next[key];
        }
      }
      return next;
    });
  };

  const getJob = (input: JobKeyInput): UiJob | null => {
    const state = get({ subscribe });
    return state[keyOf(input)] ?? null;
  };

  const resetAll = () => set({});

  return {
    subscribe,
    keyOf,
    upsertJob,
    startJob,
    succeedJob,
    failJob,
    clearJob,
    clearEntityJobs,
    getJob,
    resetAll
  };
}

export const jobsStore = createJobsStore();

