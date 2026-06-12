export type AddRootFolder = {
  id: string | number;
  zoneId: string | number;
  protocol: 'SMB' | 'NFS' | string;
  folderName: string;
  endpointId: number;
  rootPath: string;
};

export type AddRootEndpoint = {
  id: string | number;
  name: string;
  zoneName?: string | null;
  protocol?: 'SMB' | 'NFS' | string;
  basePath?: string | null;
  status?: string | null;
  host?: string | null;
  discoveryCount: number;
  discoveredFolders?: AddRootFolder[];
  refreshing?: boolean;
  refreshStatus?: 'idle' | 'running' | 'success' | 'failed';
  refreshMessage?: string | null;
  lastRefreshAt?: string | null;
  lastProbeAt?: string | null;
  lastProbeStatus?: string | null;
};

export type AddRootZone = {
  id: string | number;
  name: string;
  discoveryCount: number;
  endpoints: AddRootEndpoint[];
  discoveredFolders?: AddRootFolder[];
};
