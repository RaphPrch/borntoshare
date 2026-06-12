import { writable } from 'svelte/store';

export type SelectionState = {
  selectedStorageRootId: number | null;
  selectedStorageEndpointId: number | null;
  selectedIdentitySourceId: number | null;
  selectedSiteId: number | null;
  selectedZoneId: number | null;
};

const initialState = (): SelectionState => ({
  selectedStorageRootId: null,
  selectedStorageEndpointId: null,
  selectedIdentitySourceId: null,
  selectedSiteId: null,
  selectedZoneId: null
});

function createSelectionStore() {
  const { subscribe, set, update } = writable<SelectionState>(initialState());

  return {
    subscribe,

    resetAll() {
      set(initialState());
    },

    resetStorage() {
      update((state) => ({
        ...state,
        selectedStorageRootId: null,
        selectedStorageEndpointId: null
      }));
    },

    resetIdentity() {
      update((state) => ({
        ...state,
        selectedIdentitySourceId: null
      }));
    },

    resetLocations() {
      update((state) => ({
        ...state,
        selectedSiteId: null,
        selectedZoneId: null
      }));
    },

    setSelectedStorageRootId(id: number | null) {
      update((state) => ({ ...state, selectedStorageRootId: id }));
    },

    setSelectedStorageEndpointId(id: number | null) {
      update((state) => ({ ...state, selectedStorageEndpointId: id }));
    },

    setSelectedIdentitySourceId(id: number | null) {
      update((state) => ({ ...state, selectedIdentitySourceId: id }));
    },

    setSelectedSiteId(id: number | null) {
      update((state) => ({ ...state, selectedSiteId: id }));
    },

    setSelectedZoneId(id: number | null) {
      update((state) => ({ ...state, selectedZoneId: id }));
    }
  };
}

export const selectionStore = createSelectionStore();

