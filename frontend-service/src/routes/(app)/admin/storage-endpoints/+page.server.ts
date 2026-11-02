import { redirect } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';
import type { StorageEndpointContext } from '$lib/api/storage-endpoints';
import { apiServerGetList } from '$lib/server/api-server';
import { requireAuth } from '$lib/server/require-auth';

/** No home of its own: the list and the page of a server, opened on the one to look at first. */
export const load: PageServerLoad = async (event) => {
  await requireAuth(event);
  const rows = await apiServerGetList<StorageEndpointContext>('/storage-endpoints/context', event);
  if (!rows.length) return { empty: true };
  const failing = (row: StorageEndpointContext) => /fail|error|unreach/i.test(String(row.last_probe_status ?? ''));
  const ordered = [...rows].sort(
    (a, b) =>
      Number(failing(b)) - Number(failing(a)) ||
      String(a.zone_name ?? '').localeCompare(String(b.zone_name ?? '')) ||
      String(a.storage_endpoint_name ?? '').localeCompare(String(b.storage_endpoint_name ?? ''))
  );
  throw redirect(302, `/admin/storage-endpoints/${ordered[0].storage_endpoint_id}`);
};
