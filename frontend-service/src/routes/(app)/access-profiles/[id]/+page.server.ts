import { redirect } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';
import { requireAuth } from '$lib/utils/requireAuth.server';

export const load: PageServerLoad = async (event) => {
  await requireAuth(event);
  const id = Number(event.params.id);
  if (!id || Number.isNaN(id)) {
    throw redirect(302, '/storage-roots');
  }
  throw redirect(308, `/storage-roots`);
};
