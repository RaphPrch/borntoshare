import { writable } from 'svelte/store';

export type StorageEndpointsUiState = {
  selectedType: string;
  search: string;
  currentPage: number;
};

const initialState = (): StorageEndpointsUiState => ({
  selectedType: 'all',
  search: '',
  currentPage: 1
});

function createStorageEndpointsUiStore() {
  const { subscribe, set, update } = writable<StorageEndpointsUiState>(initialState());

  return {
    subscribe,

    resetAll() {
      set(initialState());
    },

    setSelectedType(selectedType: string) {
      update((state) => ({ ...state, selectedType }));
    },

    setSearch(search: string) {
      update((state) => ({ ...state, search }));
    },

    setCurrentPage(currentPage: number) {
      const normalized = Number(currentPage);
      update((state) => ({
        ...state,
        currentPage: Number.isFinite(normalized) && normalized > 0 ? Math.floor(normalized) : 1
      }));
    }
  };
}

export const storageEndpointsUiStore = createStorageEndpointsUiStore();
