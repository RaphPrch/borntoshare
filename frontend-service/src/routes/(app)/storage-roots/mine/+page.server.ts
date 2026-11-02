import type { PageServerLoad } from './$types';
import { apiServerGetData, apiServerGetList } from '$lib/server/api-server';
import { requireAuth } from '$lib/server/require-auth';

/** Folders a user reaches through their requests: in force, waiting, and those of the people they asked for. */
export const load: PageServerLoad = async (event) => {
  const me = await requireAuth(event);
  const [rows, dfsPaths] = await Promise.all([
    apiServerGetList<Record<string, any>>('/access-requests', event),
    apiServerGetData<Record<string, string>>('/storage-roots/dfs-paths', event).catch(() => ({}) as Record<string, string>)
  ]);
  const myId = Number(me.id ?? 0);
  const mine = rows.filter((row) => Number(row?.requester_identity_id ?? 0) === myId);
  const pick = (row: Record<string, any>) => ({
    request_id: Number(row.request_id ?? 0),
    storage_root_name: String(row.storage_root_name ?? '—'),
    // The DFS path when the folder is reached through a namespace: the one users know
    target_path: String((dfsPaths ?? {})[String(row.storage_root_id ?? '')] ?? row.target_path ?? ''),
    permission: String(row.permission ?? ''),
    expires_at: row.expires_at ?? null,
    created_at: row.created_at ?? null,
    requested_for: String(row.requested_for_display ?? ''),
    status: String(row.status ?? '').toLowerCase()
  });
  return {
    inForce: mine.filter((row) => String(row.status ?? '').toLowerCase() === 'approved').map(pick),
    waiting: mine.filter((row) => String(row.status ?? '').toLowerCase() === 'pending').map(pick),
    isAdmin: me.is_admin === true
  };
};
