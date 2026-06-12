import type { PageServerLoad } from './$types';

import type { StorageEndpointContext, StorageEndpointOverview } from '$lib/api/storage-endpoints';
import { apiServerGetList } from '$lib/server/api-server';
import { requireAuth } from '$lib/utils/requireAuth.server';
import { redirect } from '@sveltejs/kit';

export const load: PageServerLoad = async (event) => {
  await requireAuth(event);

  const rows = await apiServerGetList<StorageEndpointContext>('/storage-endpoints/context', event);
  const endpoints: StorageEndpointOverview[] = rows.map((row) => ({
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

  const firstEndpointId = Number(
    (Array.isArray(endpoints) ? endpoints : [])[0]?.id ??
    (Array.isArray(endpoints) ? endpoints : [])[0]?.storage_endpoint_id ??
    0
  );

  if (Number.isFinite(firstEndpointId) && firstEndpointId > 0) {
    throw redirect(302, `/admin/storage-endpoints/${firstEndpointId}`);
  }

  return {
    endpoints
  };
};
