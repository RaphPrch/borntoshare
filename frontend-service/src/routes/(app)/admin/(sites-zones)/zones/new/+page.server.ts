import type { PageServerLoad } from './$types';
import { apiServerGetData } from '$lib/server/api-server';
import { requireAuth } from '$lib/server/require-auth';

type Source = { id: number; name: string; ou: string; template: string };

export const load: PageServerLoad = async (event) => {
  await requireAuth(event);
  const parent = await event.parent();
  const zones = (Array.isArray(parent.zones) ? parent.zones : []) as Array<{ id?: number; name?: string; code?: string | null }>;
  // The rule of each existing zone, to start a new zone from it
  const sources: Source[] = await Promise.all(
    zones.slice(0, 50).map(async (zone) => {
      const id = Number(zone?.id ?? 0);
      const [policy, naming] = await Promise.all([
        apiServerGetData<{ base_ou_dn?: string | null; static_ou_dn?: string | null } | null>(`/zones/${id}/provisioning-policy`, event).catch(() => null),
        apiServerGetData<{ template?: string | null; override_enabled?: boolean | number | null } | null>(`/naming-policies/zones/${id}`, event).catch(() => null)
      ]);
      return {
        id,
        name: String(zone?.name ?? ''),
        ou: String(policy?.base_ou_dn ?? policy?.static_ou_dn ?? '').trim(),
        template: naming?.override_enabled ? String(naming?.template ?? '').trim() : ''
      };
    })
  );
  const global = (parent as { namingPolicyGlobal?: { template?: string | null; group_prefix?: string | null } | null }).namingPolicyGlobal ?? null;
  return {
    sources: sources.filter((source) => source.id > 0),
    takenNames: zones.map((zone) => String(zone?.name ?? '').trim().toLowerCase()).filter(Boolean),
    takenCodes: zones.map((zone) => String(zone?.code ?? '').trim().toUpperCase()).filter(Boolean),
    globalTemplate: String(global?.template ?? '').trim(),
    groupPrefix: String(global?.group_prefix ?? 'B2S').trim()
  };
};
