import type { PageServerLoad } from './$types';
import { redirect, error } from '@sveltejs/kit';
import { requireAuth } from '$lib/utils/requireAuth.server';

export const load: PageServerLoad = async (event) => {
  await requireAuth(event);

  const id = Number(event.params.id);
  if (Number.isNaN(id)) {
    throw error(400, 'Invalid storage endpoint id');
  }

  throw redirect(307, `/admin/storage-endpoints/${id}?openEdit=1`);
};
