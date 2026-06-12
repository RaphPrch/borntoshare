import { redirect } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';
import { requireAuth } from '$lib/utils/requireAuth.server';

export const load: PageServerLoad = async (event) => {
  await requireAuth(event);
  throw redirect(308, '/storage-roots');
};
