<script module lang="ts">
  export type ZonesSidebarZone = {
    id: number;
    name: string;
    code?: string | null;
    is_active?: boolean;
    healthLabel?: "ok" | "warning";
    endpointCount?: number;
  };
</script>

<script lang="ts">
  import { t } from '$lib/i18n';
  import EntitySidebarTree, {
    type EntitySidebarGroup
  } from "$lib/components/entity/EntitySidebarTree.svelte";

  export let zones: ZonesSidebarZone[] = [];
  export let selectedZoneId: number | null = null;
  export let onSelectZone: ((id: number) => void) | null = null;

  let q = "";
  let filter = "all";

  const norm = (v?: string | null) => (v ?? "").toLowerCase().trim();

  $: sortedZones = [...zones].sort((a, b) => {
    const byName = String(a?.name ?? "").localeCompare(String(b?.name ?? ""), "fr", {
      sensitivity: "base",
    });
    if (byName !== 0) return byName;
    return Number(a?.id ?? 0) - Number(b?.id ?? 0);
  });

  $: query = norm(q);
  $: filtered = sortedZones.filter((z) => {
    const haystack = [norm(z.name), norm(z.code)].join(" ");
    return (query === "" || haystack.includes(query)) && (filter === "all" || z.healthLabel === "warning");
  });
  $: warningCount = zones.filter((z) => z.healthLabel === "warning").length;
  $: filters = [
    { key: "all", label: t("All"), count: zones.length },
    { key: "warning", label: t("Needs attention"), count: warningCount }
  ];
  const endpointsLabel = (count: number) =>
    count === 1 ? t("1 endpoint") : t("{count} endpoints", { count });

  $: treeGroups = [{
    id: 'zones',
    label: t('Zones'),
    items: filtered.map((zone) => ({
      id: zone.id,
      label: zone.name,
      subtitle: [zone.code, endpointsLabel(Number(zone.endpointCount ?? 0))].filter(Boolean).join(" · "),
      icon: "bi-diagram-2",
      tone: zone.healthLabel === 'warning' ? 'warning' : 'healthy',
      indicator: null,
      raw: zone
    }))
  }] satisfies EntitySidebarGroup[];
</script>

<EntitySidebarTree
  ariaLabel={t('Zones')}
  searchPlaceholder={t('Search zone or code')}
  searchAriaLabel={t('Search zone or code')}
  emptyLabel={t('No zone matches your search.')}
  query={q}
  groups={treeGroups}
  selectedId={selectedZoneId}
  grouped={false}
  {filters}
  activeFilter={filter}
  onFilter={(key) => (filter = key)}
  onQueryChange={(value) => (q = value)}
  onSelect={(id) => onSelectZone?.(Number(id))}
/>
