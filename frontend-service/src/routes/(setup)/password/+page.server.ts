import { redirect } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';
import { requireAuth } from '$lib/server/require-auth';

// The temporary password of a local account (the first administrator, set by the installation wizard)
export const load: PageServerLoad = async (event) => {
  const me = await requireAuth(event);
  if (!me.must_change_password) throw redirect(302, '/dashboard');
  return { username: me.username };
};
