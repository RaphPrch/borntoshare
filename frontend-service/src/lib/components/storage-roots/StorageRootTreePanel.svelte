<script lang="ts">
  

  import { onMount } from 'svelte';
  import { t } from '$lib/i18n';
  import EntitySidebarTree, {
    type EntityTreeBadge,
    type EntityTreeNode
  } from '$lib/components/entity/EntitySidebarTree.svelte';
  import { matchesFolderQuery, parseFolderQuery } from '$lib/components/storage-roots/folder-query';
  import FolderQueryAssist from '$lib/components/storage-roots/FolderQueryAssist.svelte';
  import StorageRootPeek from '$lib/components/storage-roots/StorageRootPeek.svelte';
  import StorageRootContextMenu from '$lib/components/storage-roots/StorageRootContextMenu.svelte';
  import ContextMenu, { menuPositionFor, type ContextMenuItem } from '$lib/components/ui/ContextMenu.svelte';
  import type { FolderActionKind } from '$lib/components/storage-roots/StorageRootFolderActions.svelte';
  import type { StorageRootRow } from '$lib/utils/storage-roots';

  type AlertTone = 'warning' | 'error';
  type RootAlertSummary = { count: number; tone: AlertTone; label?: string } | null;
  /** Folder of a server path; `rows` are the storage roots whose path ends here */
  type PathNode = { key: string; segment: string; children: Map<string, PathNode>; rows: StorageRootRow[] };
  type Alerts = { count: number; tone: AlertTone | null };

  
  
  
  
  
  interface Props {
    /**
   * List pane of the storage roots page, like a file explorer:
   * zone > server > folders of the UNC path > storage roots (or a flat list per zone).
   */
    rows?: StorageRootRow[];
    /** « + » next to the search (see EntitySidebarTree) */
    onAdd?: (() => void) | null;
    addLabel?: string;
    query?: string;
    selectedStorageRootId?: number | null;
    rootAlertSummary?: (row: StorageRootRow) => RootAlertSummary;
    onQueryChange?: (value: string) => void;
    onSelectRoot?: (id: number) => void;
    /** Right-click menu on a storage root (platform admins): operations on its folder on the file server */
    onFolderAction?: ((kind: FolderActionKind, row: StorageRootRow) => void) | null;
    /** Right click on a server: create a share (a new folder at its root), add folders, open it (administrators) */
    onServerAction?: ((kind: 'share' | 'add-folders' | 'open', endpointId: number) => void) | null;
    /** Several folders at once (administrators): scan the sensitivity or measure them all */
    onBulkAnalysis?: ((kind: 'sensitivity' | 'measure', rows: StorageRootRow[]) => Promise<void> | void) | null;
  }

  let {
    rows = [],
    onAdd = null,
    addLabel = '',
    query = '',
    selectedStorageRootId = null,
    rootAlertSummary = () => null,
    onQueryChange = () => {},
    onSelectRoot = () => {},
    onFolderAction = null,
    onServerAction = null,
    onBulkAnalysis = null
  }: Props = $props();

  // Folders ticked (Ctrl/Cmd + click, Shift + click, the box of the row); only those still listed count
  let checked = $state(new Set<string>());
  function pruneChecked(list: StorageRootRow[]) {
    const present = new Set(list.map((row) => String(rootId(row))));
    if ([...checked].some((id) => !present.has(id))) checked = new Set([...checked].filter((id) => present.has(id)));
  }
  let bulkBusy = $state(false);
  // The tip about the multiple selection: shown until the selection was used once (remembered in this browser)
  const TIP_KEY = 'b2s.storageRoots.multiTipSeen';
  let tipSeen = $state(false);
  onMount(() => {
    try {
      tipSeen = localStorage.getItem(TIP_KEY) === '1';
    } catch {
      // Storage unavailable: the tip stays
    }
  });
  async function runBulk(kind: 'sensitivity' | 'measure', targets: StorageRootRow[]) {
    if (!onBulkAnalysis || !targets.length || bulkBusy) return;
    bulkBusy = true;
    try {
      await onBulkAnalysis(kind, targets);
    } finally {
      bulkBusy = false;
    }
  }
  const selectRows = (targets: StorageRootRow[]) => (checked = new Set(targets.map((row) => String(rootId(row)))));

  // Right click on a ticked folder while several are ticked: the menu acts on all of them
  let bulkMenuAt: { x: number; y: number } | null = $state(null);
  // The folders under each server node (its menu can select, scan or measure them)
  const serverRows = new Map<string, StorageRootRow[]>();

  // The file server behind each server node (the first SMB one; a DFS namespace takes no share)
  const serverEndpoints = new Map<string, { id: number; label: string; dfs: boolean }>();
  let serverMenu: { id: number; label: string; dfs: boolean; key: string } | null = $state(null);
  let serverMenuAt = $state({ x: 0, y: 0 });

  const VIEW_KEY = 'b2s.storageRoots.view';
  let peekRow: StorageRootRow | null = $state(null);
  let peekAnchor: HTMLElement | null = $state(null);
  let menuRow: StorageRootRow | null = $state(null);
  let menuAt = $state({ x: 0, y: 0 });
  let filter = $state('all');
  let viewMode: 'tree' | 'list' = $state('tree');

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
  const noGuardian = (row: StorageRootRow): boolean => String((row as any)?.open_alert_types ?? '').includes('missing_guardian');

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
      badges: [
        // Sensitive files found by the last scan (passwords, keys, personal or bank data, risky files)
        ...(Number((row as any)?.sensitive_files ?? 0) > 0
          ? [{ label: String((row as any).sensitive_files), tone: 'error', icon: 'bi-shield-lock',
               title: t('{count} sensitive file(s) found by the last scan', { count: Number((row as any).sensitive_files) }) }]
          : []),
        // What the folder waits for: a run in progress, or never measured / never scanned
        ...((row as any)?.measure_status === 'running' || (row as any)?.sensitivity_status === 'running'
          ? [{ label: '', tone: 'info', icon: 'bi-arrow-repeat',
               title: (row as any)?.measure_status === 'running' ? t('Measure in progress') : t('Sensitivity scan in progress') }]
          : [
              ...((row as any)?.content_size_bytes == null && (row as any)?.estimated_size_bytes == null && (row as any)?.measure_status !== 'done'
                ? [{ label: '', tone: 'neutral', icon: 'bi-rulers', title: t('Never measured') }] : []),
              ...((row as any)?.sensitive_files == null
                ? [{ label: '', tone: 'neutral', icon: 'bi-shield', title: t('Sensitivity never scanned') }] : [])
            ]),
        ...(row?.inheritance_broken === true
          ? [{ label: '', tone: 'neutral', icon: 'bi-scissors', title: t('The NTFS inheritance of this folder is disabled') }]
          : [])
      ] as EntityTreeBadge[],
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
      const endpointId = Number((row as any)?.storage_endpoint_id ?? 0);
      const dfs = String((row as any)?.storage_endpoint_type ?? '').toLowerCase() === 'dfs';
      if (endpointId && (!serverEndpoints.has(serverKey) || (serverEndpoints.get(serverKey)!.dfs && !dfs))) {
        serverEndpoints.set(serverKey, { id: endpointId, label: server, dfs });
      }
      entry.rows.push(row);
      serverRows.set(serverKey, entry.rows);
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
        // The name of the file server (FILER01), its address beside it when they differ
        label: [...server.endpoints][0] || server.label,
        hint: [...server.endpoints][0] && [...server.endpoints][0] !== server.label ? server.label : null,
        icon: 'bi-hdd-network',
        iconTone: 'server',
        contextMenu: Boolean(onServerAction) && serverEndpoints.has(key),
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

  let zoneFilter = $state('');



  let checkedRows = $derived(rows.filter((row) => checked.has(String(rootId(row)))));
  $effect.pre(() => {
    pruneChecked(rows);
  });
  $effect.pre(() => {
    if (checked.size && !tipSeen) {
      tipSeen = true;
      try {
        localStorage.setItem(TIP_KEY, '1');
      } catch {
        // Not remembered
      }
    }
  });
  // What was never done on the folders (a click filters them, then Ctrl + A and an action)
  let neverScanned = $derived(rows.filter((row) => matchesFolderQuery(row, parseFolderQuery('est:non-analyse').filters)).length);
  let neverMeasured = $derived(rows.filter((row) => matchesFolderQuery(row, parseFolderQuery('est:non-mesure').filters)).length);
  let bulkMenuItems = $derived([
    { key: 'sensitivity', label: t('Scan the sensitivity of the {count} folders', { count: checkedRows.length }), icon: 'bi-shield-lock' },
    { key: 'measure', label: t('Measure the {count} folders', { count: checkedRows.length }), icon: 'bi-rulers' },
    { key: 'clear', label: t('Clear the selection'), icon: 'bi-x-lg', separated: true }
  ] satisfies ContextMenuItem[]);
  let serverMenuRows = $derived(serverMenu ? serverRows.get(serverMenu.key) ?? [] : []);
  let serverMenuItems = $derived(serverMenu
    ? ([
        ...(onBulkAnalysis && serverMenuRows.length
          ? [
              { key: 'scan-all', label: t('Scan the sensitivity of its {count} folders', { count: serverMenuRows.length }), icon: 'bi-shield-lock' },
              { key: 'measure-all', label: t('Measure its {count} folders', { count: serverMenuRows.length }), icon: 'bi-rulers' },
              { key: 'select-all', label: t('Select its folders'), icon: 'bi-check2-square' }
            ]
          : []),
        { key: 'share', label: t('Create a share (a new folder at the root)'), icon: 'bi-folder-plus', disabled: serverMenu.dfs, separated: Boolean(onBulkAnalysis && serverMenuRows.length),
          hint: serverMenu.dfs ? t('A DFS namespace has no share of its own') : '' },
        { key: 'add-folders', label: t('Add folders'), icon: 'bi-plus-lg' },
        { key: 'open', label: t('Open the file server'), icon: 'bi-hdd-network', separated: true }
      ] satisfies ContextMenuItem[])
    : []);
  let zoneOptions = $derived([...new Map(rows.map((row) => [zoneKey(row), zoneLabel(row)])).entries()].sort((a, b) => a[1].localeCompare(b[1], 'fr')));
  $effect.pre(() => {
    if (zoneFilter && !zoneOptions.some(([key]) => key === zoneFilter)) zoneFilter = '';
  });
  let zonedRows = $derived(zoneFilter ? rows.filter((row) => zoneKey(row) === zoneFilter) : rows);
  // Express search: « tag:Finance gardien:alice est:sans-gardien … » filter the rows, the rest of the text searches the tree
  let parsed = $derived(parseFolderQuery(query));
  let visibleRows = $derived(zonedRows.filter((row) =>
    (filter === 'all' || (filter === 'review' ? toReview(row) : filter === 'no-guardian' ? noGuardian(row) : pendingCount(row) > 0)) &&
    matchesFolderQuery(row, parsed.filters)
  ));
  let nodes = $derived((() => {
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
  })());
  let filters = $derived([
    { key: 'all', label: t('All'), count: zonedRows.length },
    { key: 'review', label: t('To review'), count: zonedRows.filter(toReview).length },
    { key: 'pending', label: t('Pending requests'), count: zonedRows.filter((row) => pendingCount(row) > 0).length },
    { key: 'no-guardian', label: t('Without guardian'), count: zonedRows.filter(noGuardian).length }
  ].filter((item) => item.key === 'all' || item.count > 0));
</script>

{#if zoneOptions.length > 1}
  <div class="tree-extra">
    <select class="b2s-input" aria-label={t('Filter by zone')} bind:value={zoneFilter}>
      <option value="">{t('All zones')}</option>
      {#each zoneOptions as [key, label] (key)}<option value={key}>{label}</option>{/each}
    </select>
  </div>
{/if}

<EntitySidebarTree
  {onAdd}
  addLabel={addLabel || undefined}
  ariaLabel={t('Storage roots')}
  searchPlaceholder={t('Name, path, or tag:… gardien:… est:…')}
  searchAriaLabel={t('Search storage roots')}
  emptyLabel={t('No storage root matches your search.')}
  {query}
  matchQuery={parsed.text}
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
  multiSelect={Boolean(onBulkAnalysis)}
  {checked}
  onCheckedChange={(next) => (checked = next)}
  onContextMenu={(node, event) => {
        if (node.selectId == null) {
          // A server of the tree
          const server = serverEndpoints.get(node.key);
          if (server && onServerAction) {
            serverMenuAt = menuPositionFor(event);
            serverMenu = { ...server, key: node.key };
          }
          return;
        }
        if (checked.size > 1 && checked.has(String(node.selectId)) && onBulkAnalysis) {
          bulkMenuAt = menuPositionFor(event);
          return;
        }
        menuRow = rows.find((row) => rootId(row) === Number(node.selectId)) ?? null;
        const anchor = event.currentTarget as HTMLElement | null;
        const rect = anchor?.getBoundingClientRect();
        // The context-menu key gives no pointer position: open under the row
        menuAt = event.clientX || event.clientY ? { x: event.clientX, y: event.clientY } : { x: (rect?.left ?? 0) + 24, y: rect?.bottom ?? 0 };
      }}
  onHover={(node, anchor) => {
    peekRow = node ? rows.find((row) => rootId(row) === Number(node.selectId)) ?? null : null;
    peekAnchor = anchor;
  }}
>
  {#snippet belowSearch()}<div>
    <FolderQueryAssist {query} {rows} count={visibleRows.length} {onQueryChange} />
    {#if onBulkAnalysis && checkedRows.length}
      <div class="tree-bulk" role="region" aria-label={t('Selection')}>
        <div class="tree-bulk__head">
          <b>{t('{count} folder(s) selected', { count: checkedRows.length })}</b>
          {#if visibleRows.length > checkedRows.length}
            <button type="button" class="b2s-link-btn" onclick={() => selectRows(visibleRows)}>{t('All the {count} shown', { count: visibleRows.length })}</button>
          {/if}
          <button type="button" class="tree-bulk__close" title={t('Clear the selection')} aria-label={t('Clear the selection')} onclick={() => (checked = new Set())}>
            <i class="bi bi-x-lg" aria-hidden="true"></i>
          </button>
        </div>
        <div class="tree-bulk__actions">
          <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-secondary" disabled={bulkBusy} onclick={() => runBulk('sensitivity', checkedRows)}>
            <i class="bi bi-shield-lock" aria-hidden="true"></i>{t('Scan the sensitivity')}
          </button>
          <button type="button" class="b2s-btn b2s-btn-sm b2s-btn-secondary" disabled={bulkBusy} onclick={() => runBulk('measure', checkedRows)}>
            <i class="bi bi-rulers" aria-hidden="true"></i>{t('Measure')}
          </button>
          <a class="b2s-btn b2s-btn-sm b2s-btn-secondary" href={`/storage-roots?bulk=select&ids=${checkedRows.map((row) => rootId(row)).join(',')}`}
            title={t('Guardians, tags, ACL reading, export')}>
            <i class="bi bi-three-dots" aria-hidden="true"></i>{t('Other actions')}
          </a>
        </div>
      </div>
    {:else if onBulkAnalysis}
      {#if neverScanned || neverMeasured}
        <p class="tree-todo">
          {#if neverScanned}<button type="button" class="b2s-link-btn" onclick={() => onQueryChange('est:non-analyse')}>{t('{count} never scanned', { count: neverScanned })}</button>{/if}
          {#if neverScanned && neverMeasured} · {/if}
          {#if neverMeasured}<button type="button" class="b2s-link-btn" onclick={() => onQueryChange('est:non-mesure')}>{t('{count} never measured', { count: neverMeasured })}</button>{/if}
        </p>
      {/if}
      {#if !tipSeen}<p class="tree-tip">{t('Ctrl + click or Shift + click to select several folders; Ctrl + A takes all those shown, Escape clears.')}</p>{/if}
    {/if}
  </div>{/snippet}
</EntitySidebarTree>

<ContextMenu open={Boolean(serverMenu)} title={serverMenu?.label ?? ''} subtitle={t('File server')} items={serverMenuItems} at={serverMenuAt}
  onClose={() => (serverMenu = null)}
  onPick={(key) => {
    if (!serverMenu) return;
    if (key === 'scan-all') void runBulk('sensitivity', serverMenuRows);
    else if (key === 'measure-all') void runBulk('measure', serverMenuRows);
    else if (key === 'select-all') selectRows(serverMenuRows);
    else onServerAction?.(key === 'share' ? 'share' : key === 'add-folders' ? 'add-folders' : 'open', serverMenu.id);
  }} />

<ContextMenu open={Boolean(bulkMenuAt)} title={t('{count} folder(s) selected', { count: checkedRows.length })} items={bulkMenuItems} at={bulkMenuAt ?? { x: 0, y: 0 }}
  onClose={() => (bulkMenuAt = null)}
  onPick={(key) => {
    if (key === 'clear') checked = new Set();
    else void runBulk(key === 'measure' ? 'measure' : 'sensitivity', checkedRows);
  }} />

<StorageRootContextMenu
  row={menuRow}
  at={menuAt}
  onClose={() => (menuRow = null)}
  onOpen={(row) => onSelectRoot(rootId(row))}
  onAction={(kind, row) => onFolderAction?.(kind, row)}
  canManage={Boolean(onFolderAction)}
/>

<StorageRootPeek row={menuRow ? null : peekRow} anchor={peekAnchor} alert={peekRow ? rootAlertSummary(peekRow) : null} />

<style>
  .tree-extra { display: flex; flex-direction: column; gap: 6px; margin-bottom: 8px; }
  .tree-bulk { display: grid; gap: 8px; margin-top: 8px; padding: 8px 10px; border: 1px solid #c7d7fe; border-radius: var(--b2s-radius-md, 8px); background: #eef4ff; font-size: var(--b2s-fs-sm); }
  .tree-bulk__head { display: flex; align-items: center; gap: 8px; }
  .tree-bulk__head b { font-weight: 600; }
  .tree-bulk__close { margin-left: auto; border: 0; background: none; padding: 2px; color: var(--b2s-color-text-muted); cursor: pointer; }
  .tree-bulk__actions { display: flex; flex-wrap: wrap; gap: 6px; }
  .tree-todo { margin: 6px 0 0; font-size: var(--b2s-fs-xs); }
  .tree-tip { margin: 6px 0 0; color: var(--b2s-color-text-faint, #8a94a6); font-size: var(--b2s-fs-xs); }
</style>
