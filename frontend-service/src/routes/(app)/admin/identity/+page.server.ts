import type { PageServerLoad } from './$types';
import { requireAuth } from '$lib/server/require-auth';
import { apiServerGetData, apiServerGetList } from '$lib/server/api-server';

/** People and directory groups with a place in BornToShare, and the folders each one guards. */
export const load: PageServerLoad = async (event) => {
  const user = await requireAuth(event);
  const [payload, guardians] = await Promise.all([
    apiServerGetData<Record<string, any>>('/identity', event),
    apiServerGetList<{ identity_id: number; folders: number; sole: number }>('/identity/guardians', event).catch(() => [])
  ]);
  const items: Array<Record<string, any>> = Array.isArray(payload?.items)
    ? payload.items
    : [...(Array.isArray(payload?.users) ? payload.users : []), ...(Array.isArray(payload?.groups) ? payload.groups : [])];
  return { user, items, guardians };
};
