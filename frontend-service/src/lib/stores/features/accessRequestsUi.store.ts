import { writable } from 'svelte/store';

export type AccessRequestsTab =
  | 'all'
  | 'pending'
  | 'approved'
  | 'rejected'
  | 'revoked'
  | string;

export type AccessRequestsUiState = {
  queryText: string;
  syncedQuery: string;
  statusFilter: AccessRequestsTab;
  onlyMineToAction: boolean;
  selectedIds: number[];
};

const initialState = (): AccessRequestsUiState => ({
  queryText: '',
  syncedQuery: '',
  statusFilter: 'pending',
  onlyMineToAction: false,
  selectedIds: []
});

function uniqueIds(ids: number[]): number[] {
  return Array.from(
    new Set(
      ids
        .map((id) => Number(id))
        .filter((id) => Number.isFinite(id) && id > 0)
    )
  );
}

function createAccessRequestsUiStore() {
  const { subscribe, set, update } = writable<AccessRequestsUiState>(initialState());

  return {
    subscribe,

    resetAll() {
      set(initialState());
    },

    setQueryText(queryText: string) {
      update((state) => ({ ...state, queryText }));
    },

    setSyncedQuery(syncedQuery: string) {
      update((state) => ({ ...state, syncedQuery }));
    },

    setStatusFilter(statusFilter: AccessRequestsTab) {
      update((state) => ({ ...state, statusFilter }));
    },

    setOnlyMineToAction(value: boolean) {
      update((state) => ({ ...state, onlyMineToAction: value }));
    },

    setSelectedIds(ids: number[]) {
      update((state) => ({ ...state, selectedIds: uniqueIds(ids) }));
    },

    toggleSelectedId(id: number, selected: boolean) {
      const numeric = Number(id);
      if (!Number.isFinite(numeric) || numeric <= 0) return;
      update((state) => {
        const setIds = new Set(state.selectedIds);
        if (selected) setIds.add(numeric);
        else setIds.delete(numeric);
        return {
          ...state,
          selectedIds: Array.from(setIds)
        };
      });
    },

    clearSelectedIds() {
      update((state) => ({ ...state, selectedIds: [] }));
    }
  };
}

export const accessRequestsUiStore = createAccessRequestsUiStore();
