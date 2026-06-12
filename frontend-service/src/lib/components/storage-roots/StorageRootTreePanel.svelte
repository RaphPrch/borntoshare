<script lang="ts">
  import EntityActionButton from '$lib/components/common/EntityActionButton.svelte';
  import SearchField from '$lib/components/common/SearchField.svelte';
  import type { StorageRootRow } from '$lib/utils/storage-roots';

  type AlertTone = 'warning' | 'error';
  type RootAlertSummary = { count: number; tone: AlertTone; label?: string } | null;

  type RootNode = {
    id: number;
    row: StorageRootRow;
    children: RootNode[];
  };

  type TreeEntry = {
    key: string;
    depth: number;
    node?: RootNode;
    row?: StorageRootRow;
  };

  type ZoneNode = {
    id: string;
    label: string;
    rows: StorageRootRow[];
    roots: RootNode[];
  };

  export let rows: StorageRootRow[] = [];
  export let query = '';
  export let selectedStorageRootId: number | null = null;
  export let rootAlertSummary: (row: StorageRootRow) => RootAlertSummary = () => null;
  export let onQueryChange: (value: string) => void = () => {};
  export let onSelectRoot: (id: number) => void = () => {};
  export let onCreateRoot: () => void = () => {};
  export let onRefresh: () => void = () => {};

  const norm = (value: unknown): string => String(value ?? '').trim().toLowerCase();
  const rootId = (row: StorageRootRow): number => Number(row?.storage_root_id ?? row?.id ?? 0);
  const rootLabel = (row: StorageRootRow): string =>
    String(row?.storage_root_name ?? row?.storage_root_code ?? 'Storage root').trim() || 'Storage root';
  const zoneId = (row: StorageRootRow): string => String(row?.zone_id ?? 'unassigned-zone');
  const zoneLabel = (row: StorageRootRow): string =>
    String(row?.zone_name ?? 'Unassigned zone').trim() || 'Unassigned zone';

  const depthClass = (depth: number): string => `is-depth-${Math.min(Math.max(0, depth), 5)}`;

  const matchesQuery = (row: StorageRootRow): boolean => {
    const q = norm(query);
    if (!q) return true;
    return [
      row?.zone_name,
      row?.storage_endpoint_name,
      row?.storage_root_name,
      row?.storage_root_code,
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
      if (id <= 0) continue;
      nodes.set(id, {
        id,
        row,
        children: []
      });
    }

    const top: RootNode[] = [];
    for (const node of nodes.values()) {
      const parentId = Number(node.row?.parent_storage_root_id ?? 0);
      const parent = Number.isFinite(parentId) && parentId > 0 ? nodes.get(parentId) : null;
      if (parent) {
        parent.children.push(node);
      } else {
        top.push(node);
      }
    }

    const sortNodes = (items: RootNode[]): RootNode[] =>
      items
        .map((node) => ({ ...node, children: sortNodes(node.children) }))
        .sort((a, b) => rootLabel(a.row).localeCompare(rootLabel(b.row), 'fr', { sensitivity: 'base', numeric: true }));

    return sortNodes(top);
  };

  let collapsedZoneById: Record<string, boolean> = {};
  let collapsedRootById: Record<string, boolean> = {};

  const rootHasChildren = (node: RootNode): boolean => node.children.length > 0;

  const toggleZone = (id: string) => {
    collapsedZoneById = {
      ...collapsedZoneById,
      [id]: collapsedZoneById[id] !== true
    };
  };

  const toggleRoot = (id: number) => {
    const key = String(id);
    collapsedRootById = {
      ...collapsedRootById,
      [key]: collapsedRootById[key] !== true
    };
  };

  const flattenRootEntries = (nodes: RootNode[], collapsedRoots: Record<string, boolean>, depth = 0): TreeEntry[] => {
    const out: TreeEntry[] = [];
    for (const node of nodes) {
      out.push({ key: `root-${node.id}`, depth, node, row: node.row });
      if (collapsedRoots[String(node.id)] !== true) {
        out.push(...flattenRootEntries(node.children, collapsedRoots, depth + 1));
      }
    }
    return out;
  };

  const buildTree = (inputRows: StorageRootRow[]): ZoneNode[] => {
    const byZone = new Map<string, ZoneNode>();

    for (const row of inputRows) {
      const zid = zoneId(row);
      if (!byZone.has(zid)) {
        byZone.set(zid, {
          id: zid,
          label: zoneLabel(row),
          rows: [],
          roots: []
        });
      }

      byZone.get(zid)!.rows.push(row);
    }

    return [...byZone.values()]
      .map((zone) => ({
        id: zone.id,
        label: zone.label,
        rows: zone.rows,
        roots: buildRootNodes(zone.rows)
      }))
      .sort((a, b) => a.label.localeCompare(b.label, 'fr', { sensitivity: 'base', numeric: true }));
  };

  const aggregateAlert = (items: StorageRootRow[]): RootAlertSummary => {
    let count = 0;
    let tone: AlertTone = 'warning';

    for (const row of items) {
      const alert = rootAlertSummary(row);
      count += Number(alert?.count ?? 0);
      if (alert?.tone === 'error') tone = 'error';
    }

    return count > 0 ? { count, tone } : null;
  };

  const alertTotalCount = (inputRows: StorageRootRow[]) =>
    inputRows.reduce((total, row) => total + Number(rootAlertSummary(row)?.count ?? 0), 0);

  $: queryRows = rows.filter(matchesQuery);
  $: tree = buildTree(queryRows);
  $: footerRootCount = rows.length;
  $: footerAlertCount = alertTotalCount(rows);
</script>

<aside class="sr-clean-tree-panel" aria-label="Managed storage roots">
  <div class="sr-clean-tree-panel__head">
    <h2>Managed folders</h2>
  </div>

  <EntityActionButton
    compact={true}
    variant="primary"
    icon="bi-plus-lg"
    label="New storage root"
    className="sr-clean-tree-panel__create"
    onClick={onCreateRoot}
  />

  <SearchField
    wrapperClass="sr-clean-tree-panel__search"
    inputClass="sr-clean-tree-panel__search-input"
    placeholder="Search storage root..."
    ariaLabel="Search storage root"
    value={query}
    onChange={onQueryChange}
  />

  <div class="sr-clean-tree" role="tree">
    {#if tree.length === 0}
      <div class="sr-clean-tree__empty">No storage root matches your search.</div>
    {:else}
      {#each tree as zone (zone.id)}
        {@const zoneAlert = aggregateAlert(zone.rows)}
        {@const collapsed = collapsedZoneById[zone.id] === true}
        <section class="sr-clean-tree__zone">
          <button
            type="button"
            class="sr-clean-tree__group-row"
            aria-expanded={!collapsed}
            on:click={() => toggleZone(zone.id)}
          >
            <span class="sr-clean-tree__caret">
              <i class={`bi ${collapsed ? 'bi-caret-right-fill' : 'bi-caret-down-fill'}`} aria-hidden="true"></i>
            </span>
            <i class="bi bi-buildings sr-clean-tree__zone-icon" aria-hidden="true"></i>
            <strong>{zone.label}</strong>
            {#if zoneAlert}
              <span class={`sr-clean-tree__badge is-${zoneAlert.tone}`}>
                {zoneAlert.count > 1 ? zoneAlert.count : '!'}
              </span>
            {/if}
          </button>

          {#if !collapsed}
            <ul class="sr-clean-tree__roots">
              {#each flattenRootEntries(zone.roots, collapsedRootById) as entry (entry.key)}
                <li class={depthClass(entry.depth)}>
                  {#if entry.row && entry.node}
                    {@const alert = rootAlertSummary(entry.row)}
                    {@const rootCollapsed = collapsedRootById[String(entry.node.id)] === true}
                    {@const hasChildren = rootHasChildren(entry.node)}
                    <div class="sr-clean-tree__root-row">
                      <button
                        type="button"
                        class="sr-clean-tree__root-caret"
                        class:is-empty={!hasChildren}
                        aria-label={hasChildren ? `${rootCollapsed ? 'Expand' : 'Collapse'} ${rootLabel(entry.row)}` : undefined}
                        aria-expanded={hasChildren ? !rootCollapsed : undefined}
                        disabled={!hasChildren}
                        on:click={() => toggleRoot(entry.node!.id)}
                      >
                        {#if hasChildren}
                          <i class={`bi ${rootCollapsed ? 'bi-caret-right-fill' : 'bi-caret-down-fill'}`} aria-hidden="true"></i>
                        {/if}
                      </button>
                      <button
                        type="button"
                        class="sr-clean-tree__root-select"
                        class:active={rootId(entry.row) === Number(selectedStorageRootId ?? 0)}
                        on:click={() => onSelectRoot(rootId(entry.row))}
                      >
                        <i class="bi bi-folder-fill sr-clean-tree__folder-icon" aria-hidden="true"></i>
                        <span>{rootLabel(entry.row)}</span>
                        {#if alert}
                          <strong class={`sr-clean-tree__badge is-${alert.tone}`}>
                            {alert.count > 1 ? alert.count : '!'}
                          </strong>
                        {/if}
                      </button>
                    </div>
                  {/if}
                </li>
              {/each}
            </ul>
          {/if}
        </section>
      {/each}
    {/if}
  </div>

  <footer class="sr-clean-tree-panel__footer">
    <span>{footerRootCount} storage roots · {footerAlertCount} alerts</span>
    <button type="button" aria-label="Refresh storage roots" on:click={onRefresh}>
      <i class="bi bi-arrow-clockwise" aria-hidden="true"></i>
    </button>
  </footer>
</aside>
