import type { LayoutServerLoad, LayoutServerLoadEvent } from "./$types";
import { apiServerGetList } from "$lib/server/api-server";

const parseSelected = (raw: string | null) => {
  if (!raw) return null;
  const [kind, id] = raw.split(":");
  const parsedId = Number(id);
  if (!Number.isFinite(parsedId)) return null;
  if (kind !== "zone") return null;
  return { kind, id: parsedId } as const;
};

const parseZoneIdFromPath = (pathname: string): number | null => {
  const match = pathname.match(/\/admin\/zones\/(\d+)(?:\/|$)/);
  if (!match) return null;
  const id = Number(match[1]);
  return Number.isFinite(id) ? id : null;
};

export const load: LayoutServerLoad = async (event: LayoutServerLoadEvent) => {
  const zones = await apiServerGetList('/zones', event);
  const endpoints = await apiServerGetList<{
    zone_id?: number | null;
    zone?: { id?: number | null } | null;
    operational_state?: string | null;
    pending_requests_count?: number | null;
    identity_source_id?: number | null;
  }>('/storage-endpoints/context', event);
  // Folders with an open alert, per zone: the « to review » share of each zone
  const rootAlerts = await apiServerGetList<{ zone_id?: number | null; storage_root_id?: number | null; scope_id?: number | null }>(
    '/governance-alerts?scope_type=storage_root&status=open&limit=2000',
    event
  ).catch(() => []);
  const reviewRootsByZone = new Map<number, Set<number>>();
  for (const alert of rootAlerts) {
    const zoneId = Number(alert?.zone_id ?? 0);
    const rootId = Number(alert?.storage_root_id ?? alert?.scope_id ?? 0);
    if (zoneId > 0 && rootId > 0) {
      if (!reviewRootsByZone.has(zoneId)) reviewRootsByZone.set(zoneId, new Set());
      reviewRootsByZone.get(zoneId)!.add(rootId);
    }
  }

  const endpointRows = Array.isArray(endpoints) ? endpoints : [];
  const zoneHealthById = new Map<number, "ok" | "warning">();
  const endpointCountByZone = new Map<number, number>();
  const pendingByZone = new Map<number, number>();
  const directoriesByZone = new Map<number, Set<number>>();
  for (const endpoint of endpointRows) {
    const zoneId = Number(endpoint?.zone_id ?? endpoint?.zone?.id ?? 0);
    if (!Number.isFinite(zoneId) || zoneId <= 0) continue;
    endpointCountByZone.set(zoneId, (endpointCountByZone.get(zoneId) ?? 0) + 1);
    pendingByZone.set(zoneId, (pendingByZone.get(zoneId) ?? 0) + Number(endpoint?.pending_requests_count ?? 0));
    const sourceId = Number(endpoint?.identity_source_id ?? 0);
    if (sourceId > 0) {
      if (!directoriesByZone.has(zoneId)) directoriesByZone.set(zoneId, new Set());
      directoriesByZone.get(zoneId)!.add(sourceId);
    }
    const operationalState = String(endpoint?.operational_state ?? '').trim().toLowerCase();
    const isWarning = operationalState !== 'reachable';

    if (isWarning) {
      zoneHealthById.set(zoneId, "warning");
    } else if (!zoneHealthById.has(zoneId)) {
      zoneHealthById.set(zoneId, "ok");
    }
  }

  const zonesWithHealth = (Array.isArray(zones) ? zones : []).map((zone: any) => {
    const zoneId = Number(zone?.id ?? 0);
    const operationalSummary = String(zone?.operational_summary ?? '').trim().toLowerCase();
    return {
      ...zone,
      endpointCount: endpointCountByZone.get(zoneId) ?? 0,
      pendingRequests: pendingByZone.get(zoneId) ?? 0,
      reviewRoots: reviewRootsByZone.get(zoneId)?.size ?? 0,
      identitySourceIds: [...(directoriesByZone.get(zoneId) ?? [])],
      // Keep sidebar health semantics aligned with zone page backend summary.
      healthLabel:
        operationalSummary === 'healthy'
          ? 'ok'
          : zoneHealthById.get(zoneId) ?? 'warning',
    };
  });

  const selected = parseSelected(event.url.searchParams.get("selected"));
  const zoneIdFromPath = parseZoneIdFromPath(event.url.pathname);
  const selectedZoneId =
    zoneIdFromPath ??
    selected?.id ??
    (Array.isArray(zonesWithHealth) && zonesWithHealth.length > 0 ? Number(zonesWithHealth[0]?.id) || null : null);

  return {
    zones: zonesWithHealth,
    selectedZoneId,
  };
};
