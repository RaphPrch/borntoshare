import type { PageServerLoad } from './$types';
import type { RequestEvent } from '@sveltejs/kit';

import { apiServerGetList } from '$lib/server/api-server';
import { requireAuth } from '$lib/server/require-auth';

/** Segments of the page; `status` in the URL selects one (pending by default). */
const SEGMENTS = ['pending', 'applied', 'closed', 'all'] as const;
type Segment = (typeof SEGMENTS)[number];

export const load: PageServerLoad = async (event: RequestEvent) => {
  await requireAuth(event);

  const rawStatus = String(event.url.searchParams.get('status') ?? 'pending').toLowerCase();
  const segment: Segment = (SEGMENTS as readonly string[]).includes(rawStatus) ? (rawStatus as Segment) : 'pending';
  const query = event.url.searchParams.get('q') ?? '';

  // Every request the user may see (the API filters by role); segments, counters and search are computed by the page
  const requests = await apiServerGetList<Record<string, unknown>>('/access-requests', event);

  return { requests, segment, query };
};
