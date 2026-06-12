import type { PageServerLoad } from './$types';
import { requireAuth } from '$lib/utils/requireAuth.server';
import { redirect } from '@sveltejs/kit';

export const load: PageServerLoad = async (event) => {
  await requireAuth(event);

  throw redirect(308, '/admin/observability/events');
};
