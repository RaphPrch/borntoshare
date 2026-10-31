import { redirect } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';
import { requireAuth } from '$lib/server/require-auth';
import { apiServerGetData } from '$lib/server/api-server';
import { normalizeMe } from '$lib/types/me';

export const load: PageServerLoad = async (event) => {
  const me = normalizeMe(await requireAuth(event));
  if (!me.is_admin) throw redirect(302, '/dashboard');
  const status = await apiServerGetData<Record<string, any>>('/admin/setup/status', event);
  if (status?.completed) throw redirect(302, '/dashboard');
  return { status };
};
