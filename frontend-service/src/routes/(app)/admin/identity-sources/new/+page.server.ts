import type { PageServerLoad } from './$types';
import { requireAuth } from '$lib/server/require-auth';
import { apiServerGetList } from '$lib/server/api-server';

export const load: PageServerLoad = async (event) => {
  await requireAuth(event);
  const sources = await apiServerGetList<{ name?: string }>('/identity-sources', event);
  return { existingNames: sources.map((source) => String(source?.name ?? '')) };
};
