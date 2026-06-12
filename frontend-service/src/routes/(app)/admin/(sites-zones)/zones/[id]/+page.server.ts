import type { PageServerLoad, PageServerLoadEvent } from './$types';
import { redirect } from '@sveltejs/kit';
import { apiServerGetData, apiServerGetList } from '$lib/server/api-server';
import { requireAuth } from '$lib/utils/requireAuth.server';

export const load: PageServerLoad = async (event: PageServerLoadEvent) => {
  const zoneId = Number(event.params.id);
  if (!Number.isFinite(zoneId) || zoneId <= 0) {
    throw redirect(302, '/admin/zones');
  }

  const parentData = await event.parent();
  await requireAuth(event);

  const consoleData = await apiServerGetData(`/zones/${zoneId}/console`, event);
  const zoneNamingPolicy = await apiServerGetData(`/naming-policies/zones/${zoneId}`, event);
  const storageRootAlerts = await apiServerGetList(
    `/governance-alerts?scope_type=storage_root&status=open&limit=2000`,
    event
  ).catch(() => []);

  // Activity: non-blocking (bounded)
  const activity = await apiServerGetData(
    `/activity/by-target?target_type=zone&target_id=${zoneId}&limit=60`,
    event
  );

  return {
    zoneId,
    zone: consoleData?.zone ?? null,
    endpoints: Array.isArray(consoleData?.endpoints) ? consoleData.endpoints : [],
    storageRoots: Array.isArray(consoleData?.storage_roots) ? consoleData.storage_roots : [],
    storageRootAlerts: Array.isArray(storageRootAlerts) ? storageRootAlerts : [],
    operationalSummary: String(consoleData?.operational_summary ?? 'attention'),
    provisioningPolicy: consoleData?.provisioning_policy ?? null,
    zoneNamingPolicy: zoneNamingPolicy ?? null,
    kpis: consoleData?.kpis ?? null,
    activity,
    // reuse global datasets loaded in /admin/+layout.server.ts
    identitySources: parentData.identitySources ?? [],
    tags: parentData.tags ?? [],
    namingPolicyGlobal: parentData.namingPolicyGlobal ?? null
  };
};
