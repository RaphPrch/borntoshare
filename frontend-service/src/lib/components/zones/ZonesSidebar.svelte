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
    type EntityTreeNode
  } from "$lib/components/entity/EntitySidebarTree.svelte";

  export let zones: ZonesSidebarZone[] = [];
  /** « + » next to the search (see EntitySidebarTree) */
  export let onAdd: (() => void) | null = null;
  export let addLabel = '';
  export let selectedZoneId: number | null = null;
  export let onSelectZone: ((id: number) => void) | null = null;

  let q = "";
  let filter = "all";

  $: sortedZones = [...zones].sort((a, b) => {
    const byName = String(a?.name ?? "").localeCompare(String(b?.name ?? ""), "fr", {
      sensitivity: "base",
    });
    if (byName !== 0) return byName;
    return Number(a?.id ?? 0) - Number(b?.id ?? 0);
  });

  $: filtered = sortedZones.filter((z) => filter === "all" || z.healthLabel === "warning");
  $: warningCount = zones.filter((z) => z.healthLabel === "warning").length;
  $: filters = [
    { key: "all", label: t("All"), count: zones.length },
    { key: "warning", label: t("Needs attention"), count: warningCount }
  ];
  const endpointsLabel = (count: number) =>
    count === 1 ? t("1 endpoint") : t("{count} endpoints", { count });

  $: nodes = filtered.map((zone): EntityTreeNode => ({
    key: `zone:${zone.id}`,
    label: zone.name,
    subtitle: [zone.code, endpointsLabel(Number(zone.endpointCount ?? 0))].filter(Boolean).join(" · "),
    icon: "bi-geo-alt",
    iconTone: "zone",
    selectId: zone.id,
    dot: zone.healthLabel === "warning" ? "warning" : null,
    searchText: zone.code ?? null
  }));
</script>

<EntitySidebarTree
  {onAdd}
  addLabel={addLabel || undefined}
  ariaLabel={t('Zones')}
  searchPlaceholder={t('Search zone or code')}
  searchAriaLabel={t('Search zone or code')}
  emptyLabel={t('No zone matches your search.')}
  query={q}
  {nodes}
  selectedId={selectedZoneId}
  {filters}
  activeFilter={filter}
  onFilter={(key) => (filter = key)}
  onQueryChange={(value) => (q = value)}
  onSelect={(id) => onSelectZone?.(Number(id))}
/>
