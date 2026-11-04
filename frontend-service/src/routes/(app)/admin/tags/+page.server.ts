import type { PageServerLoad } from './$types';

import { apiServerGetData } from '$lib/server/api-server';
import { requireAuth } from '$lib/server/require-auth';

/** Tags with the folders that carry them, and how much of the governed folders they cover. */
export const load: PageServerLoad = async (event) => {
  const user = await requireAuth(event);
  const overview = await apiServerGetData<Record<string, unknown>>('/tags/overview', event);
  return { user, overview };
};
