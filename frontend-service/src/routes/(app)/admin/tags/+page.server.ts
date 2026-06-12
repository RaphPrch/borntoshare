import type { PageServerLoad } from './$types';

import { apiServerGetList } from '$lib/server/api-server';
import { requireAuth } from '$lib/utils/requireAuth.server';

export const load: PageServerLoad = async (event) => {
  const user = await requireAuth(event);

  const parentData = await event.parent();
  const parentTags = parentData?.tags;
  if (Array.isArray(parentTags)) {
    return {
      user,
      tags: parentTags
    };
  }

  const tags = await apiServerGetList('/tags', event);

  return {
    user,
    tags
  };
};
