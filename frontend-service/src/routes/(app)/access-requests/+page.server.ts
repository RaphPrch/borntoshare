import type { PageServerLoad } from './$types';
import type { RequestEvent } from '@sveltejs/kit';

import { apiServerGetData, apiServerGetList } from '$lib/server/api-server';
import { requireAuth } from '$lib/utils/requireAuth.server';

const TABS = ['pending', 'approved', 'enforced', 'revoked', 'rejected'] as const;

export const load: PageServerLoad = async (event: RequestEvent) => {
  await requireAuth(event);

  const status = event.url.searchParams.get('status') ?? undefined;
  const statusFilter = (status ?? 'pending').toLowerCase();
  const effectiveStatus = statusFilter === 'all' ? undefined : statusFilter;
  const my_action = event.url.searchParams.get('my_action');
  const overdue = event.url.searchParams.get('overdue');
  const high_impact = event.url.searchParams.get('high_impact');
  const q = event.url.searchParams.get('q') ?? undefined;

  const sharedFilters = {
    my_action: my_action ? Number(my_action) : undefined,
    overdue: overdue ? Number(overdue) : undefined,
    high_impact: high_impact ? Number(high_impact) : undefined,
    query: q
  };

  const params = new URLSearchParams();
  if (effectiveStatus) params.set('status', effectiveStatus);
  if (sharedFilters.my_action !== undefined) params.set('my_action', String(sharedFilters.my_action));
  if (sharedFilters.overdue !== undefined) params.set('overdue', String(sharedFilters.overdue));
  if (sharedFilters.high_impact !== undefined) params.set('high_impact', String(sharedFilters.high_impact));
  if (sharedFilters.query) params.set('q', sharedFilters.query);

  const requestQs = params.toString();
  const countsParams = new URLSearchParams(params);
  countsParams.delete('status');
  const countsQs = countsParams.toString();

  const [requests, tabCountsRaw] = await Promise.all([
    apiServerGetList<Record<string, unknown>>(`/access-requests${requestQs ? `?${requestQs}` : ''}`, event),
    apiServerGetData<Record<string, number>>(
      `/access-requests/counts-by-status${countsQs ? `?${countsQs}` : ''}`,
      event
    )
  ]);

  const tabCounts = TABS.reduce(
    (acc, tab) => {
      acc[tab] = Number(tabCountsRaw?.[tab] ?? 0);
      return acc;
    },
    {} as Record<string, number>
  );

  return {
    requests,
    tabCounts,
    statusFilter,
    query: q
  };
};
