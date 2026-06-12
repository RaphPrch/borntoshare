import type { PageServerLoad } from './$types';
import { requireAuth } from '$lib/utils/requireAuth.server';
import { apiServerGetList } from '$lib/server/api-server';

export const load: PageServerLoad = async (event) => {
  await requireAuth(event);

  const parentData = await event.parent();
  const parentIdentitySources = parentData?.identitySources;
  if (Array.isArray(parentIdentitySources)) {
    return {
      identity_sources: parentIdentitySources
    };
  }

  const identity_sources = await apiServerGetList('/identity-sources', event);

  return {
    identity_sources
  };
};
