import type { PageServerLoad } from './$types';
import { apiServerGetList } from '$lib/server/api-server';
import { requireAuth } from '$lib/server/require-auth';

export const load: PageServerLoad = async (event) => {
  await requireAuth(event);
  const [zones, endpoints, sources] = await Promise.all([
    apiServerGetList<Record<string, any>>('/zones', event),
    apiServerGetList<Record<string, any>>('/storage-endpoints/context', event),
    apiServerGetList<Record<string, any>>('/identity-sources', event).catch(() => [])
  ]);
  return {
    zones: zones.map((zone) => ({ id: Number(zone.id ?? zone.zone_id), name: String(zone.name ?? zone.zone_name ?? zone.code) })),
    // Hosts already declared (one endpoint per file server), and the accounts that can be reused in a zone
    endpoints: endpoints.map((row) => ({
      id: Number(row.storage_endpoint_id),
      isDfs: String(row.storage_endpoint_type ?? '').toLowerCase() === 'dfs',
      name: String(row.storage_endpoint_name ?? ''),
      host: String(row.host ?? ''),
      zoneId: Number(row.zone_id ?? 0),
      account: String(row.bind_dn ?? row.auth_username ?? ''),
      secretRef: String(row.bind_password_ref ?? row.auth_secret_ref ?? ''),
      identitySourceId: Number((row as any).identity_source_id ?? 0) || null
    })),
    sources: sources
      .filter((source) => String(source?.type ?? '').toLowerCase() === 'ad' && source?.is_active !== false)
      .map((source) => ({ id: Number(source.id), name: String(source.name ?? ''), domain: String(source.domain_name ?? '').toLowerCase() })),
    zoneId: Number(event.url.searchParams.get('zone') ?? 0) || null,
    kind: event.url.searchParams.get('kind') === 'dfs' ? 'dfs' : 'filer'
  };
};
