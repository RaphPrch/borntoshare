import type { PageServerLoad } from './$types';
import { apiServerGetList } from '$lib/server/api-server';
import { requireAuth } from '$lib/utils/requireAuth.server';

export const load: PageServerLoad = async (event) => {
  await requireAuth(event);

  const items = await apiServerGetList<any>('/activity/latest?limit=800&business_only=true', event);

  return {
    items,
    generatedAt: new Date().toISOString()
  };
};
