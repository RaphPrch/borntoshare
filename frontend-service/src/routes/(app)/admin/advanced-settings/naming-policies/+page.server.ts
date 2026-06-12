import type { PageServerLoad } from './$types';

import { requireAuth } from '$lib/utils/requireAuth.server';

export const load: PageServerLoad = async (event) => {
  await requireAuth(event);

  const parentData = await event.parent();
  const globalPolicy = parentData?.namingPolicyGlobal;

  return {
    globalPolicy
  };
};
