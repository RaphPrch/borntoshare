import type { LayoutServerLoad } from './$types';
import { error } from '@sveltejs/kit';

import { requireAuth } from '$lib/server/require-auth';
import { apiServerGetData } from '$lib/server/api-server';

export const load: LayoutServerLoad = async (event) => {
  const me = await requireAuth(event);
  if (me.is_admin !== true) {
    throw error(403, 'Reserved to the administrators of the platform');
  }

  // Ultra Gold: global admin datasets (loaded once, reused via parent())
  const [identitySources, tags, namingPolicyGlobal] = await Promise.all([
    apiServerGetData('/identity-sources', event),
    apiServerGetData('/tags', event),
    apiServerGetData('/naming-policies/global', event)
  ]);

  return {
    me,
    identitySources,
    tags,
    namingPolicyGlobal
  };
};
