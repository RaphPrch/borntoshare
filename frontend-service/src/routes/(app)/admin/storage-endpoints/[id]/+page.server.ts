import type { PageServerLoad } from './$types';
import type { StorageEndpointContext, StorageEndpointOverview } from '$lib/api/storage-endpoints';
import { apiServerGetList } from '$lib/server/api-server';
import { redirect, error } from '@sveltejs/kit';
import { requireAuth } from '$lib/utils/requireAuth.server';

export const load: PageServerLoad = async (event) => {
  await requireAuth(event);

  const parentData = await event.parent();
  const parentTags = Array.isArray(parentData?.tags) ? parentData.tags : null;

  const id = Number(event.params.id);
  if (Number.isNaN(id)) {
    throw error(400, 'Invalid storage endpoint id');
  }

  const [endpointRows, roots, tags, activity, storageRootAlerts] = await Promise.all([
    apiServerGetList<StorageEndpointContext>('/storage-endpoints/context', event),
    apiServerGetList('/storage-roots/context', event),
    parentTags ? Promise.resolve(parentTags) : apiServerGetList('/tags', event),
    apiServerGetList(`/activity/by-target?target_type=storage_endpoint&target_id=${id}&limit=120`, event),
    apiServerGetList('/governance-alerts?scope_type=storage_root&status=open&limit=2000', event).catch(() => [])
  ]);

  const endpoints: StorageEndpointOverview[] = endpointRows.map((row) => ({
    id: row.storage_endpoint_id,
    name: row.storage_endpoint_name,
    type: row.storage_endpoint_type,
    protocol: row.protocol ?? row.storage_endpoint_type ?? null,
    host: row.host ?? null,
    port: row.port ?? null,
    bind_dn: row.bind_dn ?? null,
    bind_password_ref: row.bind_password_ref ?? null,
    auth_username: row.auth_username ?? null,
    auth_secret_ref: row.auth_secret_ref ?? null,
    status: row.status ?? null,
    last_probe_status: row.last_probe_status ?? null,
    last_probe_at: row.last_probe_at ?? null,
    last_probe_message: row.last_probe_message ?? null,
    operational_state: row.operational_state ?? null,
    pending_requests_count: row.pending_requests_count ?? null,
    is_active: Boolean(row.is_active),
    zone_id: row.zone_id ?? null,
    zone_name: row.zone_name ?? null,
    roots_count: row.roots_count ?? null
  }));

  const enriched = endpoints ?? [];

  // If URL id is stale (deleted), redirect to the first endpoint.
  if (enriched.length > 0 && !enriched.some((e: any) => Number(e.id) === id)) {
    throw redirect(302, `/admin/storage-endpoints/${enriched[0].id}`);
  }

  return {
    endpoints: enriched,
    tags,
    roots,
    storageRootAlerts: Array.isArray(storageRootAlerts) ? storageRootAlerts : [],
    activity,
    pendingRequests: []
  };
};
