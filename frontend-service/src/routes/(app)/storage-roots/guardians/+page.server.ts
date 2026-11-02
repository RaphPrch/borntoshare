import { error } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';
import { apiServerGetData, apiServerGetList } from '$lib/server/api-server';
import { requireAuth } from '$lib/server/require-auth';

export const load: PageServerLoad = async (event) => {
  const me = await requireAuth(event);
  if (me.is_admin !== true) throw error(403, 'Reserved to the administrators of the platform');

  event.depends('app:storage-roots-guardians');
  const [roots, alerts, identity, settings] = await Promise.all([
    apiServerGetList<Record<string, any>>('/storage-roots/context', event),
    apiServerGetList<Record<string, any>>('/governance-alerts?scope_type=storage_root&status=open&limit=2000', event),
    apiServerGetData<{ users?: Record<string, any>[]; items?: Record<string, any>[] }>('/identity', event).catch(() => null),
    apiServerGetData<{ governance?: { minGuardians?: number } }>('/admin/config/advanced', event).catch(() => null)
  ]);
  const missing = new Map(
    alerts
      .filter((alert) => alert?.alert_type === 'missing_guardian')
      .map((alert) => [Number(alert.storage_root_id ?? alert.scope_id), alert])
  );
  const people = identity?.users ?? (identity?.items ?? []).filter((row) => row?.type !== 'group');
  return {
    roots: roots
      .map((root) => ({ root, id: Number(root.storage_root_id ?? root.id) }))
      .filter(({ id }) => missing.has(id))
      .map(({ root, id }) => ({
        id,
        name: String(root.storage_root_name ?? root.name ?? id),
        path: String(root.root_path ?? ''),
        zone: String(root.zone_name ?? ''),
        guardians: Number(missing.get(id)?.metadata_json?.guardians ?? 0)
      })),
    people: people
      .filter((row) => String(row?.status ?? 'active').toLowerCase() !== 'inactive')
      .map((row) => ({ id: Number(row.id), label: String(row.display_name || row.username || row.id), hint: String(row.email || row.username || '') })),
    minGuardians: Number(settings?.governance?.minGuardians ?? 2)
  };
};
