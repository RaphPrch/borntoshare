<script lang="ts">
  import { onMount } from 'svelte';
  import { t } from '$lib/i18n';
  import EntitySidebarTree, {
    type EntityTreeBadge,
    type EntityTreeNode
  } from '$lib/components/entity/EntitySidebarTree.svelte';
  import type { StorageRootRow } from '$lib/utils/storage-roots';

  type AlertTone = 'warning' | 'error';
  type RootAlertSummary = { count: number; tone: AlertTone; label?: string } | null;
  /** Folder of a server path; `rows` are the storage roots whose path ends here */
  type PathNode = { key: string; segment: string; children: Map<string, PathNode>; rows: StorageRootRow[] };
  type Alerts = { count: number; tone: AlertTone | null };

  /**
   * List pane of the storage roots page, like a file explorer:
   * zone > server > folders of the UNC path > storage roots (or a flat list per zone).
   */
  export let rows: StorageRootRow[] = [];
  /** « + » next to the search (see EntitySidebarTree) */
  export let onAdd: (() => void) | null = null;
  export let addLabel = '';
  export let query = '';
  export let selectedStorageRootId: number | null = null;
  export let rootAlertSummary: (row: StorageRootRow) => RootAlertSummary = () => null;
  export let onQueryChange: (value: string) => void = () => {};
  export let onSelectRoot: (id: number) => void = () => {};

  const VIEW_KEY = 'b2s.storageRoots.view';
  let filter = 'all';
  let viewMode: 'tree' | 'list' = 'tree';

  onMount(() => {
    try {
      if (localStorage.getItem(VIEW_KEY) === 'list') viewMode = 'list';
    } catch {
      // Storage unavailable: tree by default
    }
  });

  function setViewMode(mode: 'tree' | 'list'): void {
    viewMode = mode;
    try {
      localStorage.setItem(VIEW_KEY, mode);
    } catch {
      // Not remembered
    }
  }

  const byLabel = (a: { label: string }, b: { label: string }): number =>
    a.label.localeCompare(b.label, 'fr', { sensitivity: 'base', numeric: true });
  const rootId = (row: StorageRootRow): number => Number(row?.storage_root_id ?? row?.id ?? 0);
  const rootLabel = (row: StorageRootRow): string =>
    String(row?.storage_root_name ?? row?.storage_root_code ?? t('Storage root')).trim() || t('Storage root');
  const rootPath = (row: StorageRootRow): string => String(row?.root_path ?? row?.normalized_root_path ?? '').trim();
  const zoneKey = (row: StorageRootRow): string => String(row?.zone_id ?? 'unassigned-zone');
  const zoneLabel = (row: StorageRootRow): string => String(row?.zone_name ?? t('Unassigned zone')).trim() || t('Unassigned zone');
  const endpointLabel = (row: StorageRootRow): string => String(row?.storage_endpoint_name ?? '').trim();
  const alertCount = (row: StorageRootRow): number => Number(rootAlertSummary(row)?.count ?? 0);
  const pendingCount = (row: StorageRootRow): number => Number(row?.pending_validation_count ?? 0);
  // \\server\share\folder (or /server/share/folder) -> [server, share, folder]
  const pathSegments = (path: string): string[] => path.split(/[\\/]+/).filter(Boolean);

  const countLabel = (count: number): EntityTreeBadge => ({ label: String(count), title: t('{count} storage roots', { count }) });

  /** One indicator per root, the most urgent one (blocking alert, then pending request, then warning); both on hover */
  function rowBadges(row: StorageRootRow): EntityTreeBadge[] {
    const alert = rootAlertSummary(row);
    const alerts = alert && alert.count > 0 ? alert.count : 0;
    const pending = pendingCount(row);
    if (!alerts && !pending) return [];
    const title = [
      alerts ? (alert?.label ?? t('{count} alerts', { count: alerts })) : '',
      pending ? t('{count} pending requests', { count: pending }) : ''
    ].filter(Boolean).join(' · ');
    if (alerts && alert?.tone === 'error') return [{ label: String(alerts), tone: 'error', icon: 'bi-exclamation-triangle-fill', title }];
    if (pending) return [{ label: String(pending), tone: 'info', icon: 'bi-hourglass-split', title }];
    return [{ label: String(alerts), tone: alert?.tone ?? 'warning', icon: 'bi-exclamation-triangle-fill', title }];
  }

  function sumAlerts(items: StorageRootRow[]): Alerts {
    let count = 0;
    let tone: AlertTone | null = null;
    for (const row of items) {
      const alert = rootAlertSummary(row);
      if (!alert || alert.count <= 0) continue;
      count += alert.count;
      tone = tone === 'error' || alert.tone === 'error' ? 'error' : 'warning';
    }
    return { count, tone };
  }

  // Totals of a collapsed zone or server stay quiet (coloured icon, no background): the roots carry the full badge
  const alertBadges = ({ count, tone }: Alerts): EntityTreeBadge[] =>
    count > 0 && tone ? [{ label: String(count), tone: tone === 'error' ? 'error-quiet' : 'warning-quiet', icon: 'bi-exclamation-triangle-fill', title: t('{count} alerts', { count }) }] : [];

  function rootNode(row: StorageRootRow, key: string, subtitle: string | null = null): EntityTreeNode {
    return {
      key,
      label: rootLabel(row),
      subtitle,
      // The name may be cut in the tree: full name and path on hover
      title: [rootLabel(row), rootPath(row)].filter(Boolean).join('\n') || null,
      icon: 'bi-folder2',
      iconTone: 'root',
      selectId: rootId(row),
      badges: rowBadges(row),
      searchText: [
        rootPath(row),
        row?.storage_root_code,
        endpointLabel(row),
        ...(Array.isArray(row?.tags) ? row.tags.map((tag: any) => tag?.label ?? tag?.name ?? tag?.code) : [])
      ].filter(Boolean).join(' ')
    };
  }

  const descendantRows = (node: PathNode): StorageRootRow[] => [
    ...node.rows,
    ...[...node.children.values()].flatMap(descendantRows)
  ];

  // Folder of the path -> tree node; a root keeps its own entry, single-child plain folders are merged (corp\hr)
  function folderNode(node: PathNode, label = node.segment): EntityTreeNode[] {
    const children = [...node.children.values()];
    if (node.rows.length === 0 && children.length === 1 && children[0].rows.length === 0) {
      return folderNode(children[0], `${label}\\${children[0].segment}`);
    }
    const childNodes = children.flatMap((child) => folderNode(child)).sort(byLabel);
    if (node.rows.length === 0) {
      return [{
        key: node.key,
        label,
        icon: 'bi-folder2',
        iconTone: 'folder',
        muted: true,
        collapsedBadges: alertBadges(sumAlerts(descendantRows(node))),
        children: childNodes
      }];
    }
    // Usually one root per path; duplicates are listed side by side
    return node.rows.map((row, position) => ({
      ...rootNode(row, position === 0 ? node.key : `${node.key}#${rootId(row)}`),
      children: position === 0 ? childNodes : [],
      collapsedBadges: position === 0 ? alertBadges(sumAlerts(children.flatMap(descendantRows))) : []
    }));
  }

  function serverNodes(zoneId: string, zoneRows: StorageRootRow[]): EntityTreeNode[] {
    const servers = new Map<string, { label: string; endpoints: Set<string>; tree: PathNode; rows: StorageRootRow[] }>();
    for (const row of zoneRows) {
      const segments = pathSegments(rootPath(row));
      const server = segments[0] ?? (endpointLabel(row) || t('Unknown server'));
      const serverKey = `z:${zoneId}|s:${server.toLowerCase()}`;
      if (!servers.has(serverKey)) {
        servers.set(serverKey, {
          label: server,
          endpoints: new Set(),
          tree: { key: serverKey, segment: server, children: new Map(), rows: [] },
          rows: []
        });
      }
      const entry = servers.get(serverKey)!;
      if (endpointLabel(row)) entry.endpoints.add(endpointLabel(row));
      entry.rows.push(row);
      let cursor = entry.tree;
      for (const segment of segments.slice(1)) {
        const id = segment.toLowerCase();
        if (!cursor.children.has(id)) {
          cursor.children.set(id, { key: `${cursor.key}\\${id}`, segment, children: new Map(), rows: [] });
        }
        cursor = cursor.children.get(id)!;
      }
      cursor.rows.push(row);
    }
    return [...servers.entries()]
      .map(([key, server]): EntityTreeNode => ({
        key,
        label: server.label,
        hint: [...server.endpoints].join(' · ') || null,
        icon: 'bi-hdd-network',
        iconTone: 'server',
        badges: [countLabel(server.rows.length)],
        collapsedBadges: alertBadges(sumAlerts(server.rows)),
        // A root on the share itself (\\server only) stays directly under the server
        children: [
          ...server.tree.rows.map((row) => rootNode(row, `${key}#${rootId(row)}`)),
          ...[...server.tree.children.values()].flatMap((child) => folderNode(child)).sort(byLabel)
        ]
      }))
      .sort(byLabel);
  }

  $: visibleRows = rows.filter((row) =>
    filter === 'all' || (filter === 'alerts' ? alertCount(row) > 0 : pendingCount(row) > 0)
  );

  $: nodes = (() => {
    const zones = new Map<string, { label: string; rows: StorageRootRow[] }>();
    for (const row of visibleRows) {
      const key = zoneKey(row);
      if (!zones.has(key)) zones.set(key, { label: zoneLabel(row), rows: [] });
      zones.get(key)!.rows.push(row);
    }
    return [...zones.entries()]
      .map(([id, zone]): EntityTreeNode => ({
        key: `z:${id}`,
        label: zone.label,
        icon: 'bi-geo-alt',
        iconTone: 'zone',
        badges: [countLabel(zone.rows.length)],
        collapsedBadges: alertBadges(sumAlerts(zone.rows)),
        children:
          viewMode === 'tree'
            ? serverNodes(id, zone.rows)
            : zone.rows.map((row) => rootNode(row, `z:${id}|r:${rootId(row)}`, rootPath(row) || null)).sort(byLabel)
      }))
      .sort(byLabel);
  })();

  $: filters = [
    { key: 'all', label: t('All'), count: rows.length },
    { key: 'alerts', label: t('With alerts'), count: rows.filter((row) => alertCount(row) > 0).length },
    { key: 'pending', label: t('Pending requests'), count: rows.filter((row) => pendingCount(row) > 0).length }
  ];
</script>

<EntitySidebarTree
  {onAdd}
  addLabel={addLabel || undefined}
  ariaLabel={t('Storage roots')}
  searchPlaceholder={t('Search name or path…')}
  searchAriaLabel={t('Search storage roots')}
  emptyLabel={t('No storage root matches your search.')}
  {query}
  {nodes}
  selectedId={selectedStorageRootId}
  {filters}
  activeFilter={filter}
  onFilter={(key) => (filter = key)}
  storageKey="b2s.storageRoots.tree"
  defaultExpandDepth={0}
  {viewMode}
  onViewMode={setViewMode}
  {onQueryChange}
  onSelect={(id) => onSelectRoot(Number(id))}
/>
