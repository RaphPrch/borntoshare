<script lang="ts">
  import EntitySidebarTree, {
    type EntitySidebarGroup
  } from "$lib/components/common/EntitySidebarTree.svelte";

  export type ZonesSidebarZone = {
    id: number;
    name: string;
    code?: string | null;
    is_active?: boolean;
    healthLabel?: "ok" | "warning";
  };

  export let zones: ZonesSidebarZone[] = [];
  export let selectedZoneId: number | null = null;
  export let onSelectZone: ((id: number) => void) | null = null;
  export let onCreateZone: (() => void) | null = null;

  let q = "";

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
    const t = [norm(z.name), norm(z.code)].join(" ");
    return query === "" || t.includes(query);
  });

  $: treeGroups = [{
    id: 'zones',
    label: 'Zones',
    items: filtered.map((zone) => ({
      id: zone.id,
      label: zone.name,
      secondary: zone.code ?? null,
      tone: zone.healthLabel === 'warning' ? 'warning' : 'healthy',
      indicator: null,
      raw: zone
    }))
  }] satisfies EntitySidebarGroup[];
</script>

<EntitySidebarTree
  ariaLabel="Zones sidebar"
  createLabel="New zone"
  searchPlaceholder="Search zone or code"
  searchAriaLabel="Search zone or code"
  emptyLabel="No zone matches your search."
  query={q}
  groups={treeGroups}
  selectedId={selectedZoneId}
  grouped={false}
  onCreate={onCreateZone}
  onQueryChange={(value) => (q = value)}
  onSelect={(id) => onSelectZone?.(Number(id))}
/>
