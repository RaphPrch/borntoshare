<script lang="ts">
  import { t } from '$lib/i18n';
  import EntitySidebarTree, {
    type EntitySidebarGroup,
    type EntitySidebarItem
  } from '$lib/components/entity/EntitySidebarTree.svelte';
  import type { StorageRootRow } from '$lib/utils/storage-roots';

  type AlertTone = 'warning' | 'error';
  type RootAlertSummary = { count: number; tone: AlertTone; label?: string } | null;
  type RootNode = { id: number; row: StorageRootRow; children: RootNode[] };

  /** List pane of the storage roots page: roots grouped by zone, sub-folders indented under their parent. */
  export let rows: StorageRootRow[] = [];
  export let query = '';
  export let selectedStorageRootId: number | null = null;
  export let rootAlertSummary: (row: StorageRootRow) => RootAlertSummary = () => null;
  export let onQueryChange: (value: string) => void = () => {};
  export let onSelectRoot: (id: number) => void = () => {};

  let filter = 'all';
  let collapsedZones: Record<string, boolean> = {};

  const norm = (value: unknown): string => String(value ?? '').trim().toLowerCase();
  const rootId = (row: StorageRootRow): number => Number(row?.storage_root_id ?? row?.id ?? 0);
  const rootLabel = (row: StorageRootRow): string =>
    String(row?.storage_root_name ?? row?.storage_root_code ?? t('Storage root')).trim() || t('Storage root');
  const zoneKey = (row: StorageRootRow): string => String(row?.zone_id ?? 'unassigned-zone');
  const zoneLabel = (row: StorageRootRow): string => String(row?.zone_name ?? t('Unassigned zone')).trim() || t('Unassigned zone');
  const alertCount = (row: StorageRootRow): number => Number(rootAlertSummary(row)?.count ?? 0);

  const matchesQuery = (row: StorageRootRow): boolean => {
    const q = norm(query);
    if (!q) return true;
    return [
      row?.zone_name,
      row?.storage_endpoint_name,
      row?.storage_root_name,
      row?.storage_root_code,
      (row as any)?.root_path,
      ...(Array.isArray(row?.tags) ? row.tags.map((tag: any) => tag?.label ?? tag?.name ?? tag?.code) : [])
    ]
      .map(norm)
      .join(' ')
      .includes(q);
  };

  const buildRootNodes = (inputRows: StorageRootRow[]): RootNode[] => {
    const nodes = new Map<number, RootNode>();
    for (const row of inputRows) {
      const id = rootId(row);
      if (id > 0) nodes.set(id, { id, row, children: [] });
    }
    const top: RootNode[] = [];
    for (const node of nodes.values()) {
      const parent = nodes.get(Number(node.row?.parent_storage_root_id ?? 0));
      if (parent) parent.children.push(node);
      else top.push(node);
    }
    const sortNodes = (items: RootNode[]): RootNode[] =>
      items
        .map((node) => ({ ...node, children: sortNodes(node.children) }))
        .sort((a, b) => rootLabel(a.row).localeCompare(rootLabel(b.row), 'fr', { sensitivity: 'base', numeric: true }));
    return sortNodes(top);
  };

  const flatten = (nodes: RootNode[], depth = 0): EntitySidebarItem[] =>
    nodes.flatMap((node) => {
      const alert = rootAlertSummary(node.row);
      const item: EntitySidebarItem = {
        id: node.id,
        label: rootLabel(node.row),
        subtitle: String((node.row as any)?.root_path ?? (node.row as any)?.normalized_root_path ?? '') || null,
        icon: node.children.length > 0 ? 'bi-folder2-open' : 'bi-folder2',
        depth,
        tone: 'healthy',
        indicator: alert && alert.count > 0
          ? { kind: alert.tone, label: alert.label ?? t('{count} alerts', { count: alert.count }) }
          : null,
        raw: node.row
      };
      return [item, ...flatten(node.children, depth + 1)];
    });

  $: visibleRows = rows.filter((row) => matchesQuery(row) && (filter === 'all' || alertCount(row) > 0));
  $: groups = (() => {
    const byZone = new Map<string, { label: string; rows: StorageRootRow[] }>();
    for (const row of visibleRows) {
      const key = zoneKey(row);
      if (!byZone.has(key)) byZone.set(key, { label: zoneLabel(row), rows: [] });
      byZone.get(key)!.rows.push(row);
    }
    return [...byZone.entries()]
      .map(([id, zone]): EntitySidebarGroup => ({
        id,
        label: zone.label,
        count: zone.rows.length,
        warningCount: zone.rows.reduce((total, row) => total + alertCount(row), 0),
        items: flatten(buildRootNodes(zone.rows))
      }))
      .sort((a, b) => a.label.localeCompare(b.label, 'fr', { sensitivity: 'base', numeric: true }));
  })();
  $: rootsWithAlerts = rows.filter((row) => alertCount(row) > 0).length;
  $: filters = [
    { key: 'all', label: t('All'), count: rows.length },
    { key: 'alerts', label: t('With alerts'), count: rootsWithAlerts }
  ];
</script>

<EntitySidebarTree
  ariaLabel={t('Storage roots')}
  searchPlaceholder={t('Search storage roots…')}
  searchAriaLabel={t('Search storage roots')}
  emptyLabel={t('No storage root matches your search.')}
  {query}
  {groups}
  selectedId={selectedStorageRootId}
  itemIcon="bi-folder2"
  {filters}
  activeFilter={filter}
  onFilter={(key) => (filter = key)}
  isOpenGroup={(id) => collapsedZones[String(id)] !== true}
  onToggleGroup={(id) => (collapsedZones = { ...collapsedZones, [String(id)]: collapsedZones[String(id)] !== true })}
  onQueryChange={onQueryChange}
  onSelect={(id) => onSelectRoot(Number(id))}
/>
