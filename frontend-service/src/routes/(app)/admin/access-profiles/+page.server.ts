import type { PageServerLoad } from './$types';
import { redirect } from '@sveltejs/kit';
import { requireAuth } from '$lib/utils/requireAuth.server';

export const load: PageServerLoad = async (event) => {
  await requireAuth(event);
  throw redirect(308, '/storage-roots');
};
