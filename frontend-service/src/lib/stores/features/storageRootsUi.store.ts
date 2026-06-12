import { writable } from 'svelte/store';

export type StorageRootsDetailTab = 'overview' | 'effective-access' | 'activity';
export type StorageRootsQuickFilter = 'all' | 'alerts' | 'no_owner' | 'unreachable';

export type StorageRootsUiState = {
  query: string;
  selectedStorageRootId: number | null;
  openZoneById: Record<number, boolean>;
  detailTab: StorageRootsDetailTab;
  quickFilter: StorageRootsQuickFilter;
};

const initialState = (): StorageRootsUiState => ({
  query: '',
  selectedStorageRootId: null,
  openZoneById: {},
  detailTab: 'overview',
  quickFilter: 'all'
});

function createStorageRootsUiStore() {
  const { subscribe, set, update } = writable<StorageRootsUiState>(initialState());

  return {
    subscribe,

    resetAll() {
      set(initialState());
    },

    setQuery(query: string) {
      update((state) => ({ ...state, query }));
    },

    setSelectedStorageRootId(id: number | null) {
      update((state) => ({ ...state, selectedStorageRootId: id }));
    },

    setDetailTab(tab: StorageRootsDetailTab) {
      update((state) => ({ ...state, detailTab: tab }));
    },

    setQuickFilter(filter: StorageRootsQuickFilter) {
      update((state) => ({ ...state, quickFilter: filter }));
    },

    setOpenZone(zoneId: number, open: boolean) {
      update((state) => ({
        ...state,
        openZoneById: {
          ...state.openZoneById,
          [zoneId]: open
        }
      }));
    },

    toggleZone(zoneId: number) {
      update((state) => {
        const current = state.openZoneById[zoneId] ?? true;
        return {
          ...state,
          openZoneById: {
            ...state.openZoneById,
            [zoneId]: !current
          }
        };
      });
    }
  };
}

export const storageRootsUiStore = createStorageRootsUiStore();
