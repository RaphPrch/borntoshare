<script lang="ts">
  import EntitySidebarTree, {
    type EntitySidebarGroup,
    type EntitySidebarItem
  } from '$lib/components/common/EntitySidebarTree.svelte';

  type EndpointRow = Record<string, unknown>;
  type EndpointZoneGroup = {
    zone_id: string | number;
    zone_name: string;
    endpoints: EndpointRow[];
  };

  export let query = '';
  export let groups: EndpointZoneGroup[] = [];
  export let selectedEndpointId: number | null = null;
  export let isOpenZone: (zoneId: string | number) => boolean = () => true;
  export let onToggleZone: (zoneId: string | number) => void = () => {};
  export let onSelectEndpoint: (id: number) => void = () => {};
  export let onCreateEndpoint: () => void = () => {};
  export let onQueryChange: (value: string) => void = () => {};
  export let showToneDot = true;
  export let endpointId: (ep: EndpointRow) => number = () => 0;
  export let endpointName: (ep: EndpointRow) => string = () => 'Endpoint';
  export let endpointTone: (ep: EndpointRow) => 'healthy' | 'warning' | 'error' = () => 'warning';
  export let endpointAlertCount: (ep: EndpointRow) => number = () => 0;
  export let endpointAlertIndicator: (ep: EndpointRow) => { kind: 'warning' | 'error'; label: string } | null = () => null;

  const hasWarningForEndpoint = (ep: EndpointRow): boolean => {
    return endpointAlertCount(ep) > 0;
  };

  const warningCountForZone = (zone: EndpointZoneGroup): number =>
    (Array.isArray(zone?.endpoints) ? zone.endpoints : []).reduce((total, ep) => total + endpointAlertCount(ep), 0);

  $: treeGroups = groups.map((zone): EntitySidebarGroup => ({
    id: zone.zone_id,
    label: zone.zone_name,
    count: zone.endpoints.length,
    warningCount: warningCountForZone(zone),
    items: zone.endpoints.map((ep): EntitySidebarItem => {
      const tone = endpointTone(ep);
      return {
        id: endpointId(ep),
        label: endpointName(ep),
        tone,
        indicator: endpointAlertIndicator(ep),
        raw: ep
      };
    })
  }));
</script>

<EntitySidebarTree
  ariaLabel="Storage endpoints sidebar"
  createLabel="New endpoint"
  searchPlaceholder="Search endpoint or zone"
  searchAriaLabel="Search endpoint or zone"
  emptyLabel="No endpoint matches your search."
  {query}
  groups={treeGroups}
  selectedId={selectedEndpointId}
  grouped={true}
  {showToneDot}
  isOpenGroup={isOpenZone}
  onToggleGroup={onToggleZone}
  onCreate={onCreateEndpoint}
  onQueryChange={onQueryChange}
  onSelect={(id) => onSelectEndpoint(Number(id))}
/>
