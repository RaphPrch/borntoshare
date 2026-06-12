import type { PrincipalSearchItem } from '../utils/principal-search';

export type IdentityBrowserSource = {
  id: number;
  name: string;
  canImportGroups: boolean;
  canRunSnapshot: boolean;
  baseDn?: string | null;
  snapshotStatus?: string | null;
  lastSnapshotAt?: string | null;
  usersCount?: number;
  groupsCount?: number;
  objectsCount?: number;
};

export type IdentityTreeNode = {
  dn: string;
  name: string;
  type?: string;
  has_children?: boolean;
  loaded?: boolean;
  children?: IdentityTreeNode[];
};

export type IdentitySearchResponse = {
  items: PrincipalSearchItem[];
  count: number;
};

export type IdentityPreview = {
  dn?: string | null;
  type?: string | null;
  display_name?: string | null;
  username?: string | null;
  upn?: string | null;
  email?: string | null;
  external_id?: string | null;
  status?: string | null;
  auth_source?: string | null;
  [k: string]: unknown;
};

export type IdentityGroupSnapshot = {
  added?: number;
  removed?: number;
  total?: number;
  [k: string]: unknown;
};

export type IdentityRoleByKey = Record<string, { guardian: boolean }>;

export type IdentityBrowserSelectionPayload = {
  sourceId: number | null;
  query: string;
  selectedKeys: string[];
  selectedItems: PrincipalSearchItem[];
  roleByKey: IdentityRoleByKey;
  importRole: 'user' | 'group';
};
