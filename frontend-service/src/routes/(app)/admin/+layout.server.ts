import type { LayoutServerLoad } from './$types';
import { redirect } from '@sveltejs/kit';

import { requireAuth } from '$lib/utils/requireAuth.server';
import { apiServerGetData } from '$lib/server/api-server';

export const load: LayoutServerLoad = async (event) => {
  const me = await requireAuth(event);
  if (me.is_admin !== true) {
    throw redirect(302, '/dashboard');
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
