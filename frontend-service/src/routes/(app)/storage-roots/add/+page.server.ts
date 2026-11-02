import { redirect } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';
import { apiServerGetData, apiServerGetList } from '$lib/server/api-server';
import { requireAuth } from '$lib/server/require-auth';

export const load: PageServerLoad = async (event) => {
  const me = await requireAuth(event);
  if (me.is_admin !== true) throw redirect(302, '/storage-roots');

  event.depends('app:storage-roots-add');
  const [endpoints, catalog, tags, identity, settings] = await Promise.all([
    apiServerGetList<Record<string, any>>('/storage-endpoints/context', event),
    apiServerGetList<Record<string, any>>('/storage-roots/discovered/servers', event),
    apiServerGetList<Record<string, any>>('/tags', event).catch(() => []),
    apiServerGetData<{ users?: Record<string, any>[]; items?: Record<string, any>[] }>('/identity', event).catch(() => null),
    apiServerGetData<{ governance?: { minGuardians?: number } }>('/admin/config/advanced', event).catch(() => null)
  ]);
  const people = identity?.users ?? (identity?.items ?? []).filter((row) => row?.type !== 'group');
  return {
    endpoints,
    catalog,
    tags: tags.map((tag) => ({ id: Number(tag.id), label: String(tag.label ?? tag.name ?? tag.code ?? tag.id) })),
    people: people
      .filter((row) => String(row?.status ?? 'active').toLowerCase() !== 'inactive')
      .map((row) => ({
        id: Number(row.id),
        label: String(row.display_name || row.username || row.id),
        hint: String(row.email || row.username || '')
      })),
    minGuardians: Number(settings?.governance?.minGuardians ?? 2)
  };
};
