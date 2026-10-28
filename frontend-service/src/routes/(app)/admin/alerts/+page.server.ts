import { redirect } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';

// Moved to Observability (single hub): keep old bookmarks working
export const load: PageServerLoad = ({ url }) => {
  const params = new URLSearchParams(url.search);
  params.set('tab', 'alerts');
  throw redirect(301, `/observability?${params}`);
};
