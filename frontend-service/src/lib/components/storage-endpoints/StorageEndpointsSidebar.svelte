<script lang="ts">
  import { goto } from '$app/navigation';
  import { t } from '$lib/i18n';
  import EntitySidebarTree, {
    type EntityTreeBadge,
    type EntityTreeNode
  } from '$lib/components/entity/EntitySidebarTree.svelte';

  type EndpointRow = Record<string, unknown>;
  type RootRow = Record<string, unknown>;
  type EndpointZoneGroup = {
    zone_id: string | number;
    zone_name: string;
    endpoints: EndpointRow[];
  };

  /** List pane of the storage endpoints page: zone > endpoint > its storage roots (links to the storage roots page). */
  export let query = '';
  /** « + » next to the search (see EntitySidebarTree) */
  export let onAdd: (() => void) | null = null;
  export let addLabel = '';
  export let groups: EndpointZoneGroup[] = [];
  export let roots: RootRow[] = [];
  export let selectedEndpointId: number | null = null;
  export let onSelectEndpoint: (id: number) => void = () => {};
  export let onQueryChange: (value: string) => void = () => {};
  export let endpointId: (ep: EndpointRow) => number = () => 0;
  export let endpointName: (ep: EndpointRow) => string = () => t('Endpoint');
  export let endpointHost: (ep: EndpointRow) => string = () => '';
  export let endpointTone: (ep: EndpointRow) => 'healthy' | 'warning' | 'error' = () => 'warning';
  export let endpointAlertCount: (ep: EndpointRow) => number = () => 0;
  export let endpointAlertIndicator: (ep: EndpointRow) => { kind: 'warning' | 'error'; label: string } | null = () => null;

  const ROOT_PREFIX = 'root:';
  let filter = 'all';

  const byLabel = (a: { label: string }, b: { label: string }): number =>
    a.label.localeCompare(b.label, 'fr', { sensitivity: 'base', numeric: true });
  const isDfs = (ep: EndpointRow) => String(ep?.type ?? ep?.storage_endpoint_type ?? ep?.endpoint_type ?? '').toLowerCase() === 'dfs';
  // « To review »: what is not healthy (a count of alerts would include every namespace with a DFS folder to manage)
  const keep = (ep: EndpointRow): boolean =>
    filter === 'all' || (filter === 'todo' ? endpointTone(ep) !== 'healthy' : endpointTone(ep) === 'error');
  // DFS01.CORP.LOCAL -> DFS01: the namespace server, named once above its namespaces
  const serverOf = (ep: EndpointRow) => (endpointHost(ep) || '—').split('.')[0].toUpperCase();

  $: rootsByEndpoint = roots.reduce((map, row) => {
    const id = Number(row?.storage_endpoint_id ?? 0);
    if (!map.has(id)) map.set(id, []);
    map.get(id)!.push(row);
    return map;
  }, new Map<number, RootRow[]>());

  function alertBadge(ep: EndpointRow): EntityTreeBadge[] {
    const indicator = endpointAlertIndicator(ep);
    const count = endpointAlertCount(ep);
    return indicator && count > 0
      // Quiet (coloured icon only): the dot beside it already carries the state of the server
      ? [{ label: String(count), tone: indicator.kind === 'error' ? 'error-quiet' : 'warning-quiet', icon: 'bi-exclamation-triangle-fill', title: indicator.label }]
      : [];
  }

  function endpointNode(ep: EndpointRow): EntityTreeNode {
    const id = endpointId(ep);
    return {
      key: `ep:${id}`,
      label: endpointName(ep),
      // A namespace sits under its server, named once: no host repeated on every line
      subtitle: isDfs(ep) ? null : endpointHost(ep) || null,
      icon: String(ep?.type ?? ep?.storage_endpoint_type ?? '').toLowerCase() === 'dfs' ? 'bi-diagram-3' : 'bi-hdd-network',
      iconTone: 'server',
      selectId: id,
      // Only what needs a look: a healthy server stays quiet
      dot: endpointTone(ep) === 'healthy' ? null : endpointTone(ep),
      badges: isDfs(ep) ? [] : alertBadge(ep),
      children: (rootsByEndpoint.get(id) ?? [])
        .map((row): EntityTreeNode => {
          const rootId = Number(row?.id ?? row?.storage_root_id ?? 0);
          const path = String(row?.root_path ?? '').trim();
          return {
            key: `ep:${id}|root:${rootId}`,
            label: String(row?.name ?? row?.storage_root_name ?? path).trim() || t('Storage root'),
            title: path ? t('{path} · open in storage roots', { path }) : null,
            icon: 'bi-folder2',
            iconTone: 'root',
            selectId: `${ROOT_PREFIX}${rootId}`,
            searchText: path
          };
        })
        .sort(byLabel)
    };
  }

  $: allEndpoints = groups.flatMap((zone) => zone.endpoints);
  $: filters = [
    { key: 'all', label: t('All'), count: allEndpoints.length },
    { key: 'todo', label: t('To review'), count: allEndpoints.filter((ep) => endpointTone(ep) !== 'healthy').length },
    { key: 'unreachable', label: t('Unreachable'), count: allEndpoints.filter((ep) => endpointTone(ep) === 'error').length }
  ];

  $: nodes = groups
    .map((zone): EntityTreeNode => {
      const endpoints = zone.endpoints.filter(keep);
      const alerts = endpoints.reduce((total, ep) => total + endpointAlertCount(ep), 0);
      return {
        key: `zone:${zone.zone_id}`,
        label: zone.zone_name,
        icon: 'bi-geo-alt',
        iconTone: 'zone',
        badges: [{ label: String(endpoints.length), title: t('{count} endpoints', { count: endpoints.length }) }],
        collapsedBadges: alerts > 0 ? [{ label: String(alerts), tone: 'warning-quiet', icon: 'bi-exclamation-triangle-fill', title: t('{count} alerts', { count: alerts }) }] : [],
        children: [
          ...endpoints.filter((ep) => !isDfs(ep)).map(endpointNode).sort(byLabel),
          ...[...new Set(endpoints.filter(isDfs).map(serverOf))].sort().map((server): EntityTreeNode => {
            const namespaces = endpoints.filter((ep) => isDfs(ep) && serverOf(ep) === server);
            const review = namespaces.filter((ep) => endpointTone(ep) !== 'healthy').length;
            return {
              key: `dfs:${zone.zone_id}:${server}`,
              label: server,
              subtitle: t('{count} DFS namespace(s)', { count: namespaces.length }),
              icon: 'bi-diagram-3',
              iconTone: 'server',
              badges: review ? [{ label: String(review), tone: 'warning-quiet', icon: 'bi-exclamation-triangle-fill', title: t('{count} to review', { count: review }) }] : [],
              children: namespaces.map(endpointNode).sort(byLabel)
            };
          })
        ]
      };
    })
    .filter((zone) => (zone.children ?? []).length > 0);

  function select(id: string | number): void {
    const value = String(id);
    if (value.startsWith(ROOT_PREFIX)) goto(`/storage-roots?selected=${value.slice(ROOT_PREFIX.length)}`);
    else onSelectEndpoint(Number(id));
  }
</script>

<EntitySidebarTree
  {onAdd}
  addLabel={addLabel || undefined}
  ariaLabel={t('Storage endpoints')}
  searchPlaceholder={t('Search endpoint, host or path…')}
  searchAriaLabel={t('Search endpoint or zone')}
  emptyLabel={t('No endpoint matches your search.')}
  {query}
  {nodes}
  selectedId={selectedEndpointId}
  {filters}
  activeFilter={filter}
  onFilter={(key) => (filter = key)}
  storageKey="b2s.storageEndpoints.tree"
  defaultExpandDepth={1}
  {onQueryChange}
  onSelect={select}
/>
