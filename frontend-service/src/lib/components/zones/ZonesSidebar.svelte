<script module lang="ts">
  export type ZonesSidebarZone = {
    id: number;
    name: string;
    code?: string | null;
    is_active?: boolean;
    healthLabel?: "ok" | "warning";
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
    const haystack = [norm(z.name), norm(z.code)].join(" ");
    return query === "" || haystack.includes(query);
  });

  $: treeGroups = [{
    id: 'zones',
    label: t('Zones'),
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
  ariaLabel={t('Zones sidebar')}
  createLabel={t('New zone')}
  searchPlaceholder={t('Search zone or code')}
  searchAriaLabel={t('Search zone or code')}
  emptyLabel={t('No zone matches your search.')}
  query={q}
  groups={treeGroups}
  selectedId={selectedZoneId}
  grouped={false}
  onCreate={onCreateZone}
  onQueryChange={(value) => (q = value)}
  onSelect={(id) => onSelectZone?.(Number(id))}
/>
