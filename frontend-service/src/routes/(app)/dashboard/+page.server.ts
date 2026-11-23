import { apiServerGetList } from '$lib/server/api-server';
import type { PageServerLoad } from './$types';
import { requireAuth } from '$lib/server/require-auth';

import {
  getDashboardPlatformOverviewServer,
  getUserDashboardMe
} from '$lib/api/dashboard';

export const load: PageServerLoad = async (event) => {
  const { fetch, setHeaders } = event;
  // Reloaded by the live updates when a request moves (layout of the app)
  event.depends('b2s:requests');
  /* ======================================================
   * NO CACHE (dashboard must always be fresh)
   * ====================================================== */
  setHeaders({
    'cache-control': 'no-store'
  });

  /* ======================================================
   * AUTH GUARD (SSR — IDENTITY IS SOURCE OF TRUTH)
   * ====================================================== */

  const me = await requireAuth(event);

  /* ======================================================
   * IDENTITY → UI MODE (V1, UI-ONLY)
   * ====================================================== */
  /**
   * IMPORTANT:
   * - UI mode ONLY (never used for security)
   * - Derived from identity capabilities
   * - Compatible with future Guardians / Policies
   */

  const mode: 'admin' | 'user' = me.is_admin === true ? 'admin' : 'user';

  /* ======================================================
   * FETCH DASHBOARD OVERVIEW (SSR — AUTHENTICATED)
   * ====================================================== */
  // USER MODE: aggregated overview
  if (mode === 'user') {
    const [payload, activities] = await Promise.all([
      getUserDashboardMe(fetch),
      // Their thread of the day: their requests, their folders and tasks (the dashboard stays usable without it)
      apiServerGetList<Record<string, unknown>>('/activity/mine?limit=150', event).catch(() => [])
    ]);

    return {
      mode,
      payload,
      activities,
      me
    };
  }

  // ADMIN MODE: platform KPI (core-service is the source of truth)
  const [stats, activities] = await Promise.all([
    getDashboardPlatformOverviewServer(event),
    // The thread of the day keeps the problems of the platform among the last business actions (10 shown);
    // the dashboard stays usable if the activity log is down
    apiServerGetList<Record<string, unknown>>('/activity/latest?limit=300&business_only=true', event).catch(() => [])
  ]);

  return {
    mode,
    payload: {
      stats: {
        ...stats
      },
      activities
    },
    me
  };
};
