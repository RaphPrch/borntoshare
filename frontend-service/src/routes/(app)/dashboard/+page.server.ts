import type { PageServerLoad } from './$types';
import { requireAuth } from '$lib/utils/requireAuth.server';

import {
  getDashboardPlatformOverviewServer,
  getUserDashboardMe
} from '$lib/api/dashboard';

export const load: PageServerLoad = async (event) => {
  const { fetch, setHeaders } = event;
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
    const payload = await getUserDashboardMe(fetch);

    return {
      mode,
      payload,
      me
    };
  }

  // ADMIN MODE: platform KPI (DAL is the source of truth)
  const stats = await getDashboardPlatformOverviewServer(event);

  return {
    mode,
    payload: {
      stats: {
        ...stats
      }
    },
    me
  };
};
