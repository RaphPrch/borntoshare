import type { PageServerLoad } from './$types';
import { error, redirect } from '@sveltejs/kit';

import { requireAuth } from '$lib/utils/requireAuth.server';

export const load: PageServerLoad = async (event) => {
  await requireAuth(event);

  const id = Number(event.params.id);
  if (!id || Number.isNaN(id)) {
    throw error(400, 'Invalid storage root id');
  }

  throw redirect(307, `/storage-roots?selected=${id}`);
};
