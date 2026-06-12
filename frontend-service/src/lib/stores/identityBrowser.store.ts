import { writable } from 'svelte/store';
import type {
  IdentityBrowserSource,
  IdentityGroupSnapshot,
  IdentityPreview,
  IdentityRoleByKey,
  IdentityTreeNode
} from '../types/identityBrowser';
import type { PrincipalSearchItem } from '../utils/principal-search';

export type IdentityBrowserState = {
  loadingSources: boolean;
  loadingTree: boolean;
  loadingSearch: boolean;
  loadingPreview: boolean;
  error: string | null;

  sources: IdentityBrowserSource[];
  selectedSourceId: number | null;

  tree: IdentityTreeNode[];
  activeDn: string | null;

  query: string;
  total: number;
  rows: PrincipalSearchItem[];

  selectedKey: string | null;
  selectedKeys: string[];
  selectedCache: Record<string, PrincipalSearchItem>;
  roleByKey: IdentityRoleByKey;

  preview: IdentityPreview | null;
  snapshot: IdentityGroupSnapshot | null;
};

type IdentityBrowserContextPatch = Partial<Pick<IdentityBrowserState, 'sources' | 'selectedSourceId' | 'error'>>;
type IdentityBrowserSelectionPatch = Partial<Pick<IdentityBrowserState, 'selectedKey' | 'selectedKeys' | 'selectedCache' | 'roleByKey'>>;

const initialState = (): IdentityBrowserState => ({
  loadingSources: false,
  loadingTree: false,
  loadingSearch: false,
  loadingPreview: false,
  error: null,

  sources: [],
  selectedSourceId: null,

  tree: [],
  activeDn: null,

  query: '',
  total: 0,
  rows: [],

  selectedKey: null,
  selectedKeys: [],
  selectedCache: {},
  roleByKey: {},

  preview: null,
  snapshot: null
});

export function createIdentityBrowserStore() {
  const { subscribe, set, update } = writable<IdentityBrowserState>(initialState());

  const updateState = (mutator: (state: IdentityBrowserState) => IdentityBrowserState) => {
    update((state) => mutator(state));
  };

  return {
    subscribe,

    resetAll() {
      set(initialState());
    },

    resetBrowserState(sourceId: number | null) {
      updateState((state) => ({
        ...state,
        selectedSourceId: sourceId,
        error: null,
        tree: [],
        activeDn: null,
        loadingTree: false,
        query: '',
        total: 0,
        rows: [],
        loadingSearch: false,
        preview: null,
        snapshot: null,
        loadingPreview: false,
        selectedKey: null
      }));
    },

    resetForSource(sourceId: number | null) {
      this.resetBrowserState(sourceId);
    },

    setContext(partial: IdentityBrowserContextPatch) {
      updateState((state) => ({
        ...state,
        ...(partial ?? {})
      }));
    },

    setSources(sources: IdentityBrowserSource[], selectedSourceId: number | null) {
      updateState((state) => ({
        ...state,
        sources,
        selectedSourceId
      }));
    },

    setLoading(flag: keyof Pick<IdentityBrowserState, 'loadingSources' | 'loadingTree' | 'loadingSearch' | 'loadingPreview'>, value: boolean) {
      updateState((state) => ({
        ...state,
        [flag]: value
      }));
    },

    setTreeLoading(value: boolean) {
      this.setLoading('loadingTree', value);
    },

    setResultsLoading(value: boolean) {
      this.setLoading('loadingSearch', value);
    },

    setPreviewLoading(value: boolean) {
      this.setLoading('loadingPreview', value);
    },

    setError(message: string | null) {
      updateState((state) => ({
        ...state,
        error: message
      }));
    },

    setTree(nodes: IdentityTreeNode[]) {
      updateState((state) => ({
        ...state,
        tree: nodes
      }));
    },

    mergeChildren(parentDn: string, children: IdentityTreeNode[]) {
      const inject = (nodes: IdentityTreeNode[]): IdentityTreeNode[] =>
        nodes.map((node) => {
          if (node.dn !== parentDn) {
            return {
              ...node,
              children: Array.isArray(node.children) ? inject(node.children) : node.children
            };
          }
          return {
            ...node,
            children,
            loaded: true,
            has_children: children.length > 0
          };
        });

      updateState((state) => ({
        ...state,
        tree: inject(state.tree)
      }));
    },

    setActiveDn(dn: string | null) {
      updateState((state) => ({
        ...state,
        activeDn: dn
      }));
    },

    setQuery(query: string) {
      updateState((state) => ({
        ...state,
        query
      }));
    },

    setResults(rows: PrincipalSearchItem[], total: number) {
      this.setRows(rows, total);
    },

    setRows(rows: PrincipalSearchItem[], total: number) {
      updateState((state) => ({
        ...state,
        rows,
        total
      }));
    },

    clearSearchAndPreview() {
      updateState((state) => ({
        ...state,
        query: '',
        rows: [],
        total: 0,
        selectedKey: null,
        preview: null,
        snapshot: null
      }));
    },

    setSelectedKey(key: string | null) {
      updateState((state) => ({
        ...state,
        selectedKey: key
      }));
    },

    setSelection(partial: IdentityBrowserSelectionPatch) {
      updateState((state) => ({
        ...state,
        ...(partial ?? {})
      }));
    },

    setSelectedItems(selectedKeys: string[], selectedCache: Record<string, PrincipalSearchItem>, roleByKey: IdentityRoleByKey) {
      updateState((state) => ({
        ...state,
        selectedKeys,
        selectedCache,
        roleByKey
      }));
    },

    setPreview(preview: IdentityPreview | null, snapshot: IdentityGroupSnapshot | null) {
      updateState((state) => ({
        ...state,
        preview,
        snapshot
      }));
    },

    setPreviewState(preview: IdentityPreview | null, snapshot: IdentityGroupSnapshot | null) {
      this.setPreview(preview, snapshot);
    }
  };
}

export const identityBrowserStore = createIdentityBrowserStore();
