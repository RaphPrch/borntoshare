import type { PageServerLoad } from './$types';
import { error } from '@sveltejs/kit';

import { apiServerGetData, apiServerGetList } from '$lib/server/api-server';
import { requireAuth } from '$lib/server/require-auth';

/** Smart policies, the tags they can set, and the folders (suggestions of the condition field). Administrators only. */
export const load: PageServerLoad = async (event) => {
  const user = await requireAuth(event);
  if (user.is_admin !== true) {
    throw error(403, 'Reserved to the administrators of the platform');
  }
  const [policies, overview, folders] = await Promise.all([
    apiServerGetList<Record<string, any>>('/policies', event),
    apiServerGetData<Record<string, any>>('/tags/overview', event).catch(() => ({ tags: [] })),
    apiServerGetList<Record<string, any>>('/storage-roots/context', event).catch(() => [])
  ]);
  return { user, policies, tags: (overview?.tags ?? []) as Array<Record<string, any>>, folders };
};
