export const endpointIdOf = (endpoint: any): number =>
  Number(endpoint?.storage_endpoint_id ?? endpoint?.id ?? 0);

export const endpointZoneIdOf = (endpoint: any): number =>
  Number(endpoint?.zone_id ?? endpoint?.zone?.id ?? 0);

export const endpointNameOf = (endpoint: any): string =>
  String(endpoint?.storage_endpoint_name ?? endpoint?.name ?? endpoint?.label ?? `Endpoint #${endpointIdOf(endpoint)}`);

export const endpointProtocolOf = (endpoint: any): 'SMB' | 'NFS' | string => {
  const value = String(endpoint?.protocol ?? endpoint?.storage_endpoint_type ?? endpoint?.type ?? 'SMB')
    .trim()
    .toUpperCase();
  return value || 'SMB';
};

export const rootLabelFromPath = (value: string): string => {
  const normalized = String(value ?? '').trim().replace(/[\\/]+$/, '');
  const chunks = normalized.split(/[\\/]/).filter(Boolean);
  return chunks[chunks.length - 1] ?? normalized;
};

export const parseSnapshotRoots = (endpoint: any): string[] => {
  const snapshot = endpoint?.capabilities?.discovered_roots_snapshot;
  const roots = Array.isArray(snapshot?.roots) ? snapshot.roots : [];
  const paths: string[] = roots
    .map((row: any) => String(row?.root_path ?? row?.path ?? '').trim())
    .filter(Boolean);

  return [...new Set<string>(paths)];
};
