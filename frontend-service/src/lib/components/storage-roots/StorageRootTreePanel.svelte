<script lang="ts">
  import { onMount } from 'svelte';
  import { t } from '$lib/i18n';
  import EntitySidebarTree, {
    type EntityTreeBadge,
    type EntityTreeNode
  } from '$lib/components/entity/EntitySidebarTree.svelte';
  import StorageRootPeek from '$lib/components/storage-roots/StorageRootPeek.svelte';
  import StorageRootContextMenu from '$lib/components/storage-roots/StorageRootContextMenu.svelte';
  import type { FolderActionKind } from '$lib/components/storage-roots/StorageRootFolderActions.svelte';
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
  /** Right-click menu on a storage root (platform admins): operations on its folder on the file server */
  export let onFolderAction: ((kind: FolderActionKind, row: StorageRootRow) => void) | null = null;

  const VIEW_KEY = 'b2s.storageRoots.view';
  let peekRow: StorageRootRow | null = null;
  let peekAnchor: HTMLElement | null = null;
  let menuRow: StorageRootRow | null = null;
  let menuAt = { x: 0, y: 0 };
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
  const pendingCount = (row: StorageRootRow): number => Number(row?.pending_validation_count ?? 0);
  // \\server\share\folder (or /server/share/folder) -> [server, share, folder]
  const pathSegments = (path: string): string[] => path.split(/[\\/]+/).filter(Boolean);

  const countLabel = (count: number): EntityTreeBadge => ({ label: String(count), title: t('{count} storage roots', { count }) });

  /** A dot only when something is to be done: red = blocking alert, orange = request to decide; details on hover */
  function rowDot(row: StorageRootRow): EntityTreeNode['dot'] {
    const alert = rootAlertSummary(row);
    if (alert && alert.count > 0 && alert.tone === 'error') return 'error';
    if (pendingCount(row) > 0) return 'warning';
    return null;
  }
  const toReview = (row: StorageRootRow): boolean => rowDot(row) !== null;

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
      // Full name, path and state in the preview shown on hover
      icon: 'bi-folder2',
      iconTone: 'root',
      selectId: rootId(row),
      dot: rowDot(row),
      // Only the exception is shown: a folder whose NTFS inheritance is disabled
      badges: row?.inheritance_broken === true
        ? [{ label: t('No inheritance'), tone: 'neutral', icon: 'bi-scissors', title: t('The NTFS inheritance of this folder is disabled') }]
        : [],
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
    filter === 'all' || (filter === 'review' ? toReview(row) : pendingCount(row) > 0)
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
    { key: 'review', label: t('To review'), count: rows.filter(toReview).length },
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
  onContextMenu={onFolderAction
    ? (node, event) => {
        menuRow = rows.find((row) => rootId(row) === Number(node.selectId)) ?? null;
        const anchor = event.currentTarget as HTMLElement | null;
        const rect = anchor?.getBoundingClientRect();
        // The context-menu key gives no pointer position: open under the row
        menuAt = event.clientX || event.clientY ? { x: event.clientX, y: event.clientY } : { x: (rect?.left ?? 0) + 24, y: rect?.bottom ?? 0 };
      }
    : null}
  onHover={(node, anchor) => {
    peekRow = node ? rows.find((row) => rootId(row) === Number(node.selectId)) ?? null : null;
    peekAnchor = anchor;
  }}
/>

<StorageRootContextMenu
  row={menuRow}
  at={menuAt}
  onClose={() => (menuRow = null)}
  onOpen={(row) => onSelectRoot(rootId(row))}
  onAction={(kind, row) => onFolderAction?.(kind, row)}
/>

<StorageRootPeek row={menuRow ? null : peekRow} anchor={peekAnchor} alert={peekRow ? rootAlertSummary(peekRow) : null} />
