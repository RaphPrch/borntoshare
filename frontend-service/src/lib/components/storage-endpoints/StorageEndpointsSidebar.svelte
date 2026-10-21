<script lang="ts">
  import { t } from '$lib/i18n';
  import EntitySidebarTree, {
    type EntitySidebarGroup,
    type EntitySidebarItem
  } from '$lib/components/entity/EntitySidebarTree.svelte';

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
  export let onQueryChange: (value: string) => void = () => {};
  export let endpointId: (ep: EndpointRow) => number = () => 0;
  export let endpointName: (ep: EndpointRow) => string = () => t('Endpoint');
  export let endpointHost: (ep: EndpointRow) => string = () => '';
  export let endpointTone: (ep: EndpointRow) => 'healthy' | 'warning' | 'error' = () => 'warning';
  export let endpointAlertCount: (ep: EndpointRow) => number = () => 0;
  export let endpointAlertIndicator: (ep: EndpointRow) => { kind: 'warning' | 'error'; label: string } | null = () => null;

  const warningCountForZone = (zone: EndpointZoneGroup): number =>
    (Array.isArray(zone?.endpoints) ? zone.endpoints : []).reduce((total, ep) => total + endpointAlertCount(ep), 0);

  let filter = 'all';
  const keep = (ep: EndpointRow): boolean =>
    filter === 'all' || (filter === 'alerts' ? endpointAlertCount(ep) > 0 : endpointTone(ep) === 'error');
  $: allEndpoints = groups.flatMap((zone) => zone.endpoints);
  $: filters = [
    { key: 'all', label: t('All'), count: allEndpoints.length },
    { key: 'alerts', label: t('With alerts'), count: allEndpoints.filter((ep) => endpointAlertCount(ep) > 0).length },
    { key: 'unreachable', label: t('Unreachable'), count: allEndpoints.filter((ep) => endpointTone(ep) === 'error').length }
  ];

  $: treeGroups = groups.map((zone): EntitySidebarGroup => ({
    id: zone.zone_id,
    label: zone.zone_name,
    count: zone.endpoints.length,
    warningCount: warningCountForZone(zone),
    items: zone.endpoints.filter(keep).map((ep): EntitySidebarItem => {
      const tone = endpointTone(ep);
      return {
        id: endpointId(ep),
        label: endpointName(ep),
        subtitle: endpointHost(ep) || null,
        icon: 'bi-hdd-network',
        tone,
        indicator: endpointAlertIndicator(ep),
        raw: ep
      };
    })
  }));
</script>

<EntitySidebarTree
  ariaLabel={t('Storage endpoints')}
  searchPlaceholder={t('Search endpoint or zone')}
  searchAriaLabel={t('Search endpoint or zone')}
  emptyLabel={t('No endpoint matches your search.')}
  {query}
  groups={treeGroups}
  selectedId={selectedEndpointId}
  grouped={true}
  {filters}
  activeFilter={filter}
  onFilter={(key) => (filter = key)}
  isOpenGroup={isOpenZone}
  onToggleGroup={onToggleZone}
  onQueryChange={onQueryChange}
  onSelect={(id) => onSelectEndpoint(Number(id))}
/>
