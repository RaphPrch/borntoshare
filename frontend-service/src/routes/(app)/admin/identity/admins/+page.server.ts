import type { PageServerLoad } from './$types';

import { apiServerGetData } from '$lib/server/api-server';
import { requireAuth } from '$lib/server/require-auth';

/** Every path to the administrator role, who takes it, and what deserves a look. */
export const load: PageServerLoad = async (event) => {
  const user = await requireAuth(event);
  const admins = await apiServerGetData<Record<string, any>>('/identity/admins', event);
  return { user, admins };
};
