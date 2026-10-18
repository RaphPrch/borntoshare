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
