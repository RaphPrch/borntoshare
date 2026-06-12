// src/routes/+layout.server.ts

import type { LayoutServerLoad } from './$types';
import { requireAuth } from '$lib/utils/requireAuth.server';
import { apiServerGetData, apiServerGetList } from '$lib/server/api-server';
import { normalizeMe } from '$lib/types/me';

export const load: LayoutServerLoad = async (event) => {
  const rawMe = await requireAuth(event);
  const me = normalizeMe(rawMe);
  let topbarAlertsCount = 0;
  let guardianRootIds: number[] = [];

  if (!me.is_admin) {
    try {
      const rows = await apiServerGetList<{ storage_root_id?: number; role?: string; identity_id?: number }>(
        '/storage-roots/effective-access',
        event
      );
      guardianRootIds = (Array.isArray(rows) ? rows : [])
        .filter((row) => String(row?.role ?? '').trim().toLowerCase() === 'guardian')
        .map((row) => Number(row?.storage_root_id ?? 0))
        .filter((value, index, all) => Number.isFinite(value) && value > 0 && all.indexOf(value) === index);
    } catch {
      guardianRootIds = [];
    }
  }

  try {
    const counts = await apiServerGetData<Record<string, number>>('/access-requests/counts-by-status', event);
    topbarAlertsCount = Number(counts?.pending ?? 0) || 0;
  } catch {
    topbarAlertsCount = 0;
  }

  /* ======================================================
   * AUTH GUARD (SSR)
   * - Identity only
   * - NO authorization logic here
   * ====================================================== */
  return {
    me,
    topbarAlertsCount,
    navigation: {
      canSeeStorageRoots: me.is_admin || guardianRootIds.length > 0,
      canSeeObservability: me.is_admin,
      canSeeAdmin: me.is_admin,
      guardianRootIds
    }
  };
};
