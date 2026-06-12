import type { PageServerLoad } from './$types';
import { redirect } from '@sveltejs/kit';

import { apiServerGetList } from '$lib/server/api-server';
import { requireAuth } from '$lib/utils/requireAuth.server';

type UserLike = {
  id?: string | number;
  is_admin?: boolean;
};

type IdentityRef = {
  identity_id?: string | number;
  id?: string | number;
  user_id?: string | number;
  owner_id?: string | number;
};

type StorageRootContextRow = {
  id?: string | number;
  storage_root_id?: string | number;
  is_visible?: boolean;
  visible?: boolean;
  visibility?: string;
  status?: string;
  guardians?: IdentityRef[];
  owners?: IdentityRef[];
};

type EffectiveAccessRow = {
  storage_root_id?: string | number;
  id?: string | number;
  identity_id?: string | number;
  role?: string;
};

/**
 * Storage Roots – server load
 *
 * Principles:
 * - Auth mandatory (centralized)
 * - Direct backend services via BFF
 * - PRODUCT READ MODELS (BFF)
 */
export const load: PageServerLoad = async (event) => {
  const parent = await event.parent();
  event.depends(
    'app:storage-roots',
    'app:storage-endpoints',
    'app:tags',
    'app:governance-alerts'
  );

  // --------------------------------------------------
  // 🔐 Auth guard (centralized)
  // --------------------------------------------------
  const user = await requireAuth(event);
  const typedUser = user as UserLike;
  const isAdmin = typedUser?.is_admin === true;
  const canSeeStorageRoots = parent?.navigation?.canSeeStorageRoots === true;

  if (!canSeeStorageRoots) {
    throw redirect(302, '/dashboard');
  }

  // --------------------------------------------------
  // 📡 Backend calls (READ MODELS)
  // --------------------------------------------------
  const [storageRootsRaw, tagsRaw, endpointsRaw, effectiveAccessRaw] = await Promise.all([
    apiServerGetList('/storage-roots/context', event),
    apiServerGetList('/tags', event),
    isAdmin ? apiServerGetList('/storage-endpoints/context', event) : Promise.resolve([]),
    isAdmin ? Promise.resolve([]) : apiServerGetList('/storage-roots/effective-access', event)
  ]);
  const storageRootAlertsRaw = await apiServerGetList(
    '/governance-alerts?scope_type=storage_root&status=open&limit=2000',
    event
  ).catch(() => []);

  const normalizeId = (v: unknown) => String(v ?? '').trim().toLowerCase();
  const meId = normalizeId(typedUser?.id);

  const isVisibleRoot = (row: StorageRootContextRow): boolean => {
    if (typeof row?.is_visible === 'boolean') return row.is_visible;
    if (typeof row?.visible === 'boolean') return row.visible;

    const visibility = String(row?.visibility ?? '').trim().toLowerCase();
    if (visibility) return visibility !== 'hidden' && visibility !== 'private';

    const status = String(row?.status ?? '').trim().toLowerCase();
    if (status) return status !== 'disabled' && status !== 'hidden' && status !== 'archived';

    return true;
  };

  const isGuardian = (row: StorageRootContextRow, normalizedUserId: string): boolean => {
    if (!normalizedUserId) return false;

    const idsFromInline = [
      ...(Array.isArray(row?.guardians) ? row.guardians : []),
      ...(Array.isArray(row?.owners) ? row.owners : []),
    ]
      .map((entry: IdentityRef) =>
        normalizeId(
          entry?.identity_id ??
          entry?.id ??
          entry?.user_id ??
          entry?.owner_id ??
          entry
        )
      )
      .filter(Boolean);

    if (idsFromInline.includes(normalizedUserId)) return true;

    const accessRows = (effectiveAccessRaw as EffectiveAccessRow[] | null) ?? [];
    const rootId = Number(row?.storage_root_id ?? row?.id ?? 0);
    if (!Number.isFinite(rootId) || rootId <= 0) return false;

    return accessRows.some((a) => {
      const accessRootId = Number(a?.storage_root_id ?? a?.id ?? 0);
      const accessIdentityId = normalizeId(a?.identity_id ?? a?.id);
      const role = String(a?.role ?? '').trim().toLowerCase();
      return (
        accessRootId === rootId &&
        accessIdentityId === normalizedUserId &&
        role === 'guardian'
      );
    });
  };

  const allStorageRoots = (storageRootsRaw as StorageRootContextRow[]) ?? [];
  const scopedStorageRoots = isAdmin
    ? allStorageRoots
    : allStorageRoots.filter((row) => isVisibleRoot(row) && isGuardian(row, meId));
  const requestedRootId = Number(event.url.searchParams.get('selected') ?? 0);
  const selectedStorageRootId = scopedStorageRoots.some((row) => Number(row?.storage_root_id ?? row?.id ?? 0) === requestedRootId)
    ? requestedRootId
    : Number(scopedStorageRoots[0]?.storage_root_id ?? scopedStorageRoots[0]?.id ?? 0);
  const storageRootActivity = selectedStorageRootId > 0
    ? await apiServerGetList(
      `/activity/by-target?target_type=storage_root&target_id=${selectedStorageRootId}&limit=200`,
      event
    ).catch(() => [])
    : [];

  return {
    user,

    storageRoots: scopedStorageRoots,
    tags: (tagsRaw as unknown[]) ?? [],
    endpoints: (endpointsRaw as unknown[]) ?? [],
    storageRootAlerts: (storageRootAlertsRaw as unknown[]) ?? [],
    storageRootActivity,
    storageRootActivityRootId: selectedStorageRootId > 0 ? selectedStorageRootId : null,
  };
};
