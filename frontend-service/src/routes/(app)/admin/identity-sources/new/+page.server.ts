import type { PageServerLoad } from './$types';
import { requireAuth } from '$lib/server/require-auth';
import { apiServerGetList } from '$lib/server/api-server';

export const load: PageServerLoad = async (event) => {
  await requireAuth(event);
  const sources = await apiServerGetList<{ name?: string; domain_name?: string; auth_enabled?: boolean; is_active?: boolean }>(
    '/identity-sources',
    event
  );
  return {
    existingNames: sources.map((source) => String(source?.name ?? '')),
    // A domain is authenticated by one active source only
    authDomains: sources
      .filter((source) => source?.auth_enabled && source?.is_active !== false && source?.domain_name)
      .map((source) => ({ name: String(source.name ?? ''), domain: String(source.domain_name).trim().toLowerCase() }))
  };
};
