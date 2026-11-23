import { redirect } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';

/** The policies moved to /policies: the former address keeps working. */
export const load: PageServerLoad = async () => {
  throw redirect(308, '/policies');
};
