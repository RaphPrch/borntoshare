// src/routes/+layout.server.ts

import { redirect } from '@sveltejs/kit';
import type { LayoutServerLoad } from './$types';
import { requireAuth } from '$lib/server/require-auth';
import { apiServerGetData, apiServerGetList } from '$lib/server/api-server';
import { normalizeMe } from '$lib/types/me';
import { redirectFor } from '$lib/utils/route-access';

export const load: LayoutServerLoad = async (event) => {
  const rawMe = await requireAuth(event);
  const me = normalizeMe(rawMe);
  // Everything the shell needs, asked at once: these calls ran one after the other on every page change
  type Access = { storage_root_id?: number; role?: string; identity_id?: number };
  const [accessRows, counts, setup, badge, publicSettings, featureList] = await Promise.all([
    me.is_admin ? Promise.resolve([] as Access[]) : apiServerGetList<Access>('/storage-roots/effective-access', event).catch(() => [] as Access[]),
    apiServerGetData<Record<string, number>>('/access-requests/counts-by-status', event).catch(() => null),
    me.is_admin ? apiServerGetData<{ completed?: boolean }>('/admin/setup/status', event).catch(() => null) : Promise.resolve(null),
    me.is_admin ? apiServerGetData<{ critical_open?: number }>('/observability/badge', event).catch(() => null) : Promise.resolve(null),
    // Banner of Advanced settings › Notifications, shown to every user
    apiServerGetData<{ banner?: { enabled?: boolean; message?: string; tone?: string } }>('/admin/config/public', event).catch(() => null),
    // Optional modules opened by a license and switched on (5S…): their menus follow
    apiServerGetData<{ features?: Array<{ key: string; enabled: boolean }> }>('/features', event).catch(() => null)
  ]);

  const guardianRootIds = (Array.isArray(accessRows) ? accessRows : [])
    .filter((row) => String(row?.role ?? '').trim().toLowerCase() === 'guardian')
    .map((row) => Number(row?.storage_root_id ?? 0))
    .filter((value, index, all) => Number.isFinite(value) && value > 0 && all.indexOf(value) === index);
  const topbarAlertsCount = Number(counts?.pending ?? 0) || 0;
  const topbarCriticalAlerts = Number(badge?.critical_open ?? 0) || 0;

  // Empty application: the administrator goes through the guided setup first
  if (me.is_admin && setup && !setup.completed) throw redirect(302, '/setup');

  const banner = publicSettings?.banner?.enabled && publicSettings.banner.message ? publicSettings.banner : null;
  const features = (featureList?.features ?? []).filter((feature) => feature.enabled).map((feature) => feature.key);
  // Unknown (the core did not answer): the governance stays shown, as on every installation before the 5S-only one
  if (!featureList) features.push('governance');

  const path = event.url.pathname;
  // A user who neither administers nor guards a folder: his requests and his folders only, not the screens about
  // the folders (monitoring, reports, 5S, exposure); an installation for the 5S only: rules of $lib/utils/route-access
  const staff = me.is_admin || guardianRootIds.length > 0;
  const target = redirectFor(path, { admin: me.is_admin, staff, features });
  if (target) throw redirect(302, target);

  return {
    me,
    banner,
    topbarAlertsCount,
    topbarCriticalAlerts,
    navigation: {
      canSeeStorageRoots: me.is_admin || guardianRootIds.length > 0,
      canSeeObservability: me.is_admin,
      canSeeAdmin: me.is_admin,
      guardianRootIds,
      features
    }
  };
};
