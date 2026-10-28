import { redirect } from '@sveltejs/kit';
import { requireAuth } from '$lib/server/require-auth';
import { apiServerGet } from '$lib/server/api-server';

const PERIODS = ['24h', '7d', '30d'];

export const load = async (event) => {
  const me = await requireAuth(event);
  if (me.is_admin !== true) throw redirect(302, '/dashboard');

  const requested = event.url.searchParams.get('period') ?? '24h';
  const period = PERIODS.includes(requested) ? requested : '24h';
  const [overview, infra] = await Promise.all([
    apiServerGet<{ data?: unknown }>(`/observability/overview?period=${period}`, event).catch(() => null),
    apiServerGet<{ data?: unknown }>('/infrastructure/overview', event).catch(() => null)
  ]);
  return { period, overview: overview?.data ?? null, infra: infra?.data ?? null };
};
