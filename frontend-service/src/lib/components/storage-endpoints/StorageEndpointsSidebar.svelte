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
  /** A server id, or « dfs-server:DFS01 » for a DFS server (its namespaces have no line of their own) */
  export let selectedEndpointId: number | string | null = null;
  export let onSelectDfsServer: (server: string, firstNamespaceId: number) => void = () => {};
  export let onSelectEndpoint: (id: number) => void = () => {};
  export let onQueryChange: (value: string) => void = () => {};
  export let endpointId: (ep: EndpointRow) => number = () => 0;
  export let endpointName: (ep: EndpointRow) => string = () => t('Endpoint');
  export let endpointHost: (ep: EndpointRow) => string = () => '';
  export let endpointTone: (ep: EndpointRow) => 'healthy' | 'warning' | 'error' = () => 'warning';
  export let endpointAlertCount: (ep: EndpointRow) => number = () => 0;
  export let endpointAlertIndicator: (ep: EndpointRow) => { kind: 'warning' | 'error'; label: string } | null = () => null;
  /** Right click on a file server (not a DFS namespace): its menu */
  export let onEndpointMenu: ((ep: EndpointRow, event: MouseEvent) => void) | null = null;

  const ROOT_PREFIX = 'root:';
  const DFS_PREFIX = 'dfs-server:';
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

  // \\corp.local\brest: the folders reached through the namespace hang under it, along their DFS path
  const capabilitiesOf = (ep: EndpointRow): Record<string, any> => {
    const raw = ep?.capabilities;
    if (typeof raw !== 'string') return (raw as Record<string, any>) ?? {};
    try {
      return JSON.parse(raw) ?? {};
    } catch {
      return {};
    }
  };
  // The context view gives the capabilities as JSON text
  const namespacePath = (ep: EndpointRow) => String(capabilitiesOf(ep)?.dfs_snapshot?.path ?? '').replace(/\\+$/, '').toLowerCase();
  type Branch = { label: string; key: string; root: RootRow | null; children: Map<string, Branch> };

  function rootNode(row: RootRow, key: string, label?: string): EntityTreeNode {
    const rootId = Number(row?.id ?? row?.storage_root_id ?? 0);
    const path = String(row?.root_path ?? '').trim();
    return {
      key,
      label: label ?? (String(row?.name ?? row?.storage_root_name ?? path).trim() || t('Storage root')),
      title: path ? t('{path} · open in storage roots', { path }) : null,
      icon: 'bi-folder2',
      iconTone: 'root',
      selectId: `${ROOT_PREFIX}${rootId}`,
      searchText: `${path} ${String(row?.dfs_path ?? '')}`
    };
  }

  function dfsChildren(ep: EndpointRow, id: number): EntityTreeNode[] {
    const prefix = namespacePath(ep);
    if (!prefix) return [];
    const top: Branch = { label: '', key: `ep:${id}`, root: null, children: new Map() };
    for (const row of roots) {
      const dfsPath = String(row?.dfs_path ?? '');
      if (!dfsPath.toLowerCase().startsWith(`${prefix}\\`)) continue;
      let branch = top;
      for (const part of dfsPath.slice(prefix.length).split('\\').filter(Boolean)) {
        const name = part.toLowerCase();
        if (!branch.children.has(name)) branch.children.set(name, { label: part, key: `${branch.key}|${name}`, root: null, children: new Map() });
        branch = branch.children.get(name)!;
      }
      branch.root = row;
    }
    const toNode = (branch: Branch): EntityTreeNode => {
      const children = [...branch.children.values()].map(toNode).sort(byLabel);
      if (branch.root) return { ...rootNode(branch.root, branch.key, branch.label), children };
      // A DFS folder level with no managed folder of its own (Corporate\…)
      return { key: branch.key, label: branch.label, icon: 'bi-folder', iconTone: 'root', children };
    };
    return [...top.children.values()].map(toNode).sort(byLabel);
  }

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
      icon: String(ep?.type ?? ep?.storage_endpoint_type ?? '').toLowerCase() === 'dfs' ? 'bi-diagram-3' : 'bi-hdd-network',
      iconTone: 'server',
      selectId: id,
      // Only what needs a look: a healthy server stays quiet
      dot: endpointTone(ep) === 'healthy' ? null : endpointTone(ep),
      badges: isDfs(ep) ? [] : alertBadge(ep),
      // Only the servers here: their folders are on the folders page (the count says how many)
      hint: (rootsByEndpoint.get(id) ?? []).length ? t('{count} folder(s)', { count: (rootsByEndpoint.get(id) ?? []).length }) : null,
      children: []
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
            // The server only: its namespaces are listed on its page, and their folders on the folders page
            return {
              key: `dfs:${zone.zone_id}:${server}`,
              label: server,
              subtitle: t('{count} DFS namespace(s)', { count: namespaces.length }),
              icon: 'bi-diagram-3',
              iconTone: 'server',
              selectId: `${DFS_PREFIX}${server}`,
              dot: namespaces.some((ep) => endpointTone(ep) === 'error') ? 'error' : null,
              badges: review ? [{ label: String(review), tone: 'warning-quiet', icon: 'bi-exclamation-triangle-fill', title: t('{count} to review', { count: review }) }] : [],
              children: []
            };
          })
        ]
      };
    })
    .filter((zone) => (zone.children ?? []).length > 0);

  function select(id: string | number): void {
    const value = String(id);
    if (value.startsWith(ROOT_PREFIX)) goto(`/storage-roots?selected=${value.slice(ROOT_PREFIX.length)}`);
    else if (value.startsWith(DFS_PREFIX)) {
      const server = value.slice(DFS_PREFIX.length);
      const first = allEndpoints.filter((ep) => isDfs(ep) && serverOf(ep) === server).map(endpointId).sort((a, b) => a - b)[0];
      if (first) onSelectDfsServer(server, first);
    } else onSelectEndpoint(Number(id));
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
  onContextMenu={onEndpointMenu ? (node, event) => {
    if (String(node.selectId).startsWith(ROOT_PREFIX) || String(node.selectId).startsWith(DFS_PREFIX)) return;
    const ep = allEndpoints.find((row) => endpointId(row) === Number(node.selectId));
    if (ep && !isDfs(ep)) onEndpointMenu?.(ep, event);
  } : null}
/>
