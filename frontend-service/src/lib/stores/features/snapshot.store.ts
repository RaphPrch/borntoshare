import { get, writable } from 'svelte/store';

export type SnapshotStatus = 'idle' | 'running' | 'success' | 'error';

export type IdentitySnapshotEntry = {
  identitySourceId: number;
  status: SnapshotStatus;
  loading: boolean;
  error: string | null;
  note: string | null;
  lastRunAt: string | null;
  lastSnapshotStatus: string | null;
  lastSnapshotVersion: number | null;
  lastSnapshotObjectsCount: number | null;
  lastSnapshotUsersCount: number | null;
  lastSnapshotGroupsCount: number | null;
  lastSnapshotMembershipsCount: number | null;
  updatedAt: string;
};

export type SnapshotState = Record<number, IdentitySnapshotEntry>;

const nowIso = () => new Date().toISOString();

const makeEntry = (identitySourceId: number): IdentitySnapshotEntry => ({
  identitySourceId,
  status: 'idle',
  loading: false,
  error: null,
  note: null,
  lastRunAt: null,
  lastSnapshotStatus: null,
  lastSnapshotVersion: null,
  lastSnapshotObjectsCount: null,
  lastSnapshotUsersCount: null,
  lastSnapshotGroupsCount: null,
  lastSnapshotMembershipsCount: null,
  updatedAt: nowIso()
});

function createSnapshotStore() {
  const { subscribe, update, set } = writable<SnapshotState>({});

  const upsert = (
    identitySourceId: number,
    patch: Partial<Omit<IdentitySnapshotEntry, 'identitySourceId' | 'updatedAt'>>
  ) => {
    if (!Number.isFinite(identitySourceId) || identitySourceId <= 0) return;

    update((state) => {
      const current = state[identitySourceId] ?? makeEntry(identitySourceId);
      return {
        ...state,
        [identitySourceId]: {
          ...current,
          ...patch,
          identitySourceId,
          updatedAt: nowIso()
        }
      };
    });
  };

  const setRunning = (identitySourceId: number, note?: string | null) =>
    upsert(identitySourceId, {
      status: 'running',
      loading: true,
      error: null,
      note: note ?? null,
      lastRunAt: nowIso()
    });

  const setSuccess = (
    identitySourceId: number,
    patch?: {
      note?: string | null;
      lastSnapshotStatus?: string | null;
      lastSnapshotVersion?: number | null;
      lastSnapshotObjectsCount?: number | null;
      lastSnapshotUsersCount?: number | null;
      lastSnapshotGroupsCount?: number | null;
      lastSnapshotMembershipsCount?: number | null;
      lastRunAt?: string | null;
    }
  ) =>
    upsert(identitySourceId, {
      status: 'success',
      loading: false,
      error: null,
      note: patch?.note ?? null,
      lastSnapshotStatus: patch?.lastSnapshotStatus ?? null,
      lastSnapshotVersion: patch?.lastSnapshotVersion ?? null,
      lastSnapshotObjectsCount: patch?.lastSnapshotObjectsCount ?? null,
      lastSnapshotUsersCount: patch?.lastSnapshotUsersCount ?? null,
      lastSnapshotGroupsCount: patch?.lastSnapshotGroupsCount ?? null,
      lastSnapshotMembershipsCount: patch?.lastSnapshotMembershipsCount ?? null,
      lastRunAt: patch?.lastRunAt ?? nowIso()
    });

  const setError = (identitySourceId: number, error: string, note?: string | null) =>
    upsert(identitySourceId, {
      status: 'error',
      loading: false,
      error,
      note: note ?? null
    });

  const clear = (identitySourceId: number) => {
    update((state) => {
      const next = { ...state };
      delete next[identitySourceId];
      return next;
    });
  };

  const getById = (identitySourceId: number): IdentitySnapshotEntry | null => {
    const state = get({ subscribe });
    return state[identitySourceId] ?? null;
  };

  return {
    subscribe,
    upsert,
    setRunning,
    setSuccess,
    setError,
    clear,
    getById,
    resetAll() {
      set({});
    }
  };
}

export const snapshotStore = createSnapshotStore();
