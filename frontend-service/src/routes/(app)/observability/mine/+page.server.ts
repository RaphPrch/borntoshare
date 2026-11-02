import type { PageServerLoad } from './$types';
import { apiServerGetList } from '$lib/server/api-server';
import { requireAuth } from '$lib/server/require-auth';

/** Monitoring of a user who is not an administrator: their actions, their requests, the folders they guard. */
export const load: PageServerLoad = async (event) => {
  await requireAuth(event);
  const events = await apiServerGetList<Record<string, any>>('/activity/mine?limit=150', event).catch(() => null);
  return { events: events ?? [], failed: events === null };
};
