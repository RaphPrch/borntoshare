import type { PageServerLoad } from './$types';
import { redirect } from '@sveltejs/kit';

export const load: PageServerLoad = async (event) => {
  const parentData = await event.parent();
  const selectedZoneId = Number(parentData?.selectedZoneId ?? 0);
  if (selectedZoneId > 0) {
    throw redirect(302, `/admin/zones/${selectedZoneId}`);
  }
  // No zones yet → stay on empty page (Svelte will render accordingly)
  return { zones: parentData?.zones ?? [], selectedZoneId: null };
};
