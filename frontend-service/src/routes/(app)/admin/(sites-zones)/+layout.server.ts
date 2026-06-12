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
  const endpoints = await apiServerGetList('/storage-endpoints/context', event);

  const endpointRows = Array.isArray(endpoints) ? endpoints : [];
  const zoneHealthById = new Map<number, "ok" | "warning">();
  for (const endpoint of endpointRows) {
    const zoneId = Number(endpoint?.zone_id ?? endpoint?.zone?.id ?? 0);
    if (!Number.isFinite(zoneId) || zoneId <= 0) continue;
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
