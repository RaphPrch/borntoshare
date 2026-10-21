import { redirect } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';

// Request details now open in the drawer of the list page; old links keep working
export const load: PageServerLoad = ({ params }) => {
  redirect(307, `/access-requests?status=all&request=${encodeURIComponent(params.id)}`);
};
