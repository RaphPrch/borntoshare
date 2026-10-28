import { requireAuth } from '$lib/server/require-auth';
import { apiServerGet } from '$lib/server/api-server';

export const load = async (event) => {
  await requireAuth(event);
  const [overview, services] = await Promise.all([
    apiServerGet<{ data?: unknown }>('/infrastructure/overview', event).catch(() => null),
    apiServerGet<{ data?: unknown }>('/infrastructure/services', event).catch(() => null)
  ]);
  return {
    overview: overview?.data ?? null,
    services: Array.isArray(services?.data) ? services.data : []
  };
};
