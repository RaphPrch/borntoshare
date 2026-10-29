<script module lang="ts">
  export type EntityTreeBadge = {
    label: string;
    tone?: 'neutral' | 'info' | 'warning' | 'error' | 'warning-quiet' | 'error-quiet';
    icon?: string | null;
    title?: string | null;
  };

  export type EntityTreeNode = {
    /** Unique key of the node in the tree (stable across reloads: it keys the expanded state) */
    key: string;
    label: string;
    /** Small muted text after the label (endpoint name, code…) */
    hint?: string | null;
    /** Second line under the label (path, host…) */
    subtitle?: string | null;
    /** Tooltip (full path…) */
    title?: string | null;
    icon?: string | null;
    iconTone?: 'zone' | 'server' | 'folder' | 'root' | 'neutral';
    /** Navigation-only node (folder of a path that is not an entity) */
    muted?: boolean;
    /** Id passed to onSelect; nodes without one only expand/collapse */
    selectId?: string | number | null;
    /** Health dot shown at the end of the row */
    dot?: 'healthy' | 'warning' | 'error' | 'neutral' | null;
    badges?: EntityTreeBadge[];
    /** Badges shown only while the node is collapsed (alerts of hidden children) */
    collapsedBadges?: EntityTreeBadge[];
    /** Extra text matched by the search */
    searchText?: string | null;
    children?: EntityTreeNode[];
  };

  export type EntitySidebarFilter = { key: string; label: string; count?: number };
</script>

<script lang="ts">
  import { onMount, tick } from 'svelte';
  import { t } from '$lib/i18n';
  import SearchField from '$lib/components/ui/SearchField.svelte';

  type Row = { node: EntityTreeNode; depth: number; parent: string | null; hasChildren: boolean; expanded: boolean };

  /**
   * List pane of the entity workspaces (zones, storage endpoints, storage roots):
   * search, quick filters and a tree in the style of a file explorer
   * (collapsible levels, guides, keyboard navigation, remembered expanded nodes).
   */
  export let ariaLabel = t('Entity list');
  export let searchPlaceholder = t('Search');
  export let searchAriaLabel = t('Search');
  export let emptyLabel = t('No item matches your search.');
  export let query = '';
  export let nodes: EntityTreeNode[] = [];
  export let selectedId: string | number | null = null;
  export let filters: EntitySidebarFilter[] = [];
  export let activeFilter = '';
  export let onFilter: (key: string) => void = () => {};
  export let onSelect: (id: string | number, node: EntityTreeNode) => void = () => {};
  export let onQueryChange: (value: string) => void = () => {};
  /** « + » next to the search: creates an item of the list (new file server, storage roots, zone) */
  export let onAdd: (() => void) | null = null;
  export let addLabel = t('Add');
  /** localStorage key of the expanded nodes (none: not remembered) */
  export let storageKey: string | null = null;
  /** Levels expanded the first time (before anything is remembered) */
  export let defaultExpandDepth = 1;
  /** Optional Tree / List switch */
  export let viewMode: 'tree' | 'list' | null = null;
  export let onViewMode: (mode: 'tree' | 'list') => void = () => {};

  let expanded = new Set<string>();
  /** Branches opened only to reveal the selection: closed again when the selection moves elsewhere */
  let autoOpened = new Set<string>();
  let initialized = false;
  let focusedKey: string | null = null;
  let treeEl: HTMLDivElement;

  const norm = (value: unknown): string => String(value ?? '').trim().toLowerCase();
  const hasChildren = (node: EntityTreeNode): boolean => Array.isArray(node.children) && node.children.length > 0;

  // Index of the full tree: parent of each key, keys of the containers, key of the selected entity
  $: index = (() => {
    const parents = new Map<string, string | null>();
    const containers: string[] = [];
    let selectedKey: string | null = null;
    const walk = (items: EntityTreeNode[], parent: string | null, depth: number) => {
      for (const node of items) {
        parents.set(node.key, parent);
        if (hasChildren(node)) {
          containers.push(node.key);
          walk(node.children ?? [], node.key, depth + 1);
        }
        if (node.selectId != null && selectedId != null && String(node.selectId) === String(selectedId)) selectedKey = node.key;
      }
    };
    walk(nodes, null, 0);
    return { parents, containers, selectedKey };
  })();
  $: isTree = index.containers.length > 0;

  function ancestors(key: string | null): string[] {
    const out: string[] = [];
    let current = key ? index.parents.get(key) ?? null : null;
    while (current) {
      out.push(current);
      current = index.parents.get(current) ?? null;
    }
    return out;
  }

  function persist(): void {
    if (!storageKey) return;
    try {
      // Branches opened automatically are not remembered: the next selection decides
      localStorage.setItem(storageKey, JSON.stringify([...expanded].filter((key) => !autoOpened.has(key))));
    } catch {
      // Private mode or blocked storage: the tree still works, it is just not remembered
    }
  }

  function setExpanded(next: Set<string>): void {
    expanded = next;
    persist();
  }

  function toggle(key: string, open?: boolean): void {
    autoOpened.delete(key);
    const next = new Set(expanded);
    const shouldOpen = open ?? !next.has(key);
    if (shouldOpen) next.add(key);
    else next.delete(key);
    setExpanded(next);
  }

  function expandAll(): void {
    setExpanded(new Set(index.containers));
  }

  function collapseAll(): void {
    autoOpened = new Set();
    setExpanded(new Set());
  }

  // Scrolls the list only (never the page) so that the row is visible
  function scrollToRow(key: string | null): void {
    const row = rowEl(key);
    const body = row?.closest<HTMLElement>('.b2s-list-pane__body');
    if (!row || !body) return;
    const top = row.offsetTop - body.offsetTop;
    if (top < body.scrollTop) body.scrollTop = top - 8;
    else if (top + row.offsetHeight > body.scrollTop + body.clientHeight) body.scrollTop = top + row.offsetHeight - body.clientHeight + 8;
  }

  async function revealSelection(): Promise<void> {
    if (!index.selectedKey) return;
    setExpanded(new Set([...expanded, ...ancestors(index.selectedKey)]));
    focusedKey = index.selectedKey;
    await tick();
    scrollToRow(index.selectedKey);
  }

  onMount(() => {
    let stored: string[] | null = null;
    if (storageKey) {
      try {
        const raw = localStorage.getItem(storageKey);
        stored = raw ? JSON.parse(raw) : null;
      } catch {
        stored = null;
      }
    }
    if (Array.isArray(stored)) {
      expanded = new Set(stored.map(String));
    } else {
      const next = new Set<string>();
      const walk = (items: EntityTreeNode[], depth: number) => {
        for (const node of items) {
          if (!hasChildren(node) || depth >= defaultExpandDepth) continue;
          next.add(node.key);
          walk(node.children ?? [], depth + 1);
        }
      };
      walk(nodes, 0);
      expanded = next;
    }
    initialized = true;
  });

  // The selected entity is always visible (deep link, Ctrl+K search, selection from another page)
  let revealedFor: string | null = null;
  $: if (initialized && index.selectedKey && index.selectedKey !== revealedFor) {
    revealedFor = index.selectedKey;
    const path = ancestors(index.selectedKey);
    const next = new Set(expanded);
    for (const key of autoOpened) {
      if (!path.includes(key)) next.delete(key);
    }
    const missing = path.filter((key) => !next.has(key));
    autoOpened = new Set([...[...autoOpened].filter((key) => path.includes(key)), ...missing]);
    for (const key of missing) next.add(key);
    setExpanded(next);
    tick().then(() => scrollToRow(index.selectedKey));
  }

  // Search: keeps matching nodes and their ancestors, and opens the branches that lead to them
  $: q = norm(query);
  const matches = (node: EntityTreeNode): boolean =>
    [node.label, node.hint, node.subtitle, node.searchText].map(norm).join(' ').includes(q);

  function filterTree(items: EntityTreeNode[]): EntityTreeNode[] {
    if (!q) return items;
    const out: EntityTreeNode[] = [];
    for (const node of items) {
      if (matches(node)) {
        out.push(node);
        continue;
      }
      const children = filterTree(node.children ?? []);
      if (children.length > 0) out.push({ ...node, children });
    }
    return out;
  }

  $: rows = (() => {
    const out: Row[] = [];
    const walk = (items: EntityTreeNode[], depth: number, parent: string | null) => {
      for (const node of items) {
        const children = hasChildren(node);
        const open = children && (q ? true : expanded.has(node.key));
        out.push({ node, depth, parent, hasChildren: children, expanded: open });
        if (open) walk(node.children ?? [], depth + 1, node.key);
      }
    };
    walk(filterTree(nodes), 0, null);
    return out;
  })();

  $: if (rows.length > 0 && (!focusedKey || !rows.some((row) => row.node.key === focusedKey))) {
    focusedKey = index.selectedKey && rows.some((row) => row.node.key === index.selectedKey) ? index.selectedKey : rows[0].node.key;
  }

  function highlight(label: string): Array<{ text: string; hit: boolean }> {
    if (!q) return [{ text: label, hit: false }];
    const parts: Array<{ text: string; hit: boolean }> = [];
    const lower = label.toLowerCase();
    let from = 0;
    let at = lower.indexOf(q);
    while (at >= 0) {
      if (at > from) parts.push({ text: label.slice(from, at), hit: false });
      parts.push({ text: label.slice(at, at + q.length), hit: true });
      from = at + q.length;
      at = lower.indexOf(q, from);
    }
    if (from < label.length) parts.push({ text: label.slice(from), hit: false });
    return parts;
  }

  const rowEl = (key: string | null): HTMLElement | null =>
    key && treeEl ? treeEl.querySelector<HTMLElement>(`[data-key="${CSS.escape(key)}"]`) : null;

  async function focusRow(key: string | null): Promise<void> {
    if (!key) return;
    focusedKey = key;
    await tick();
    rowEl(key)?.focus({ preventScroll: true });
    scrollToRow(key);
  }

  function activate(row: Row): void {
    focusedKey = row.node.key;
    if (row.node.selectId != null) onSelect(row.node.selectId, row.node);
    else if (row.hasChildren) toggle(row.node.key);
  }

  function onKeydown(event: KeyboardEvent): void {
    const position = rows.findIndex((row) => row.node.key === focusedKey);
    const row = rows[position];
    if (!row) return;
    const keyActions: Record<string, () => void> = {
      ArrowDown: () => focusRow(rows[Math.min(rows.length - 1, position + 1)].node.key),
      ArrowUp: () => focusRow(rows[Math.max(0, position - 1)].node.key),
      Home: () => focusRow(rows[0].node.key),
      End: () => focusRow(rows[rows.length - 1].node.key),
      ArrowRight: () => {
        if (row.hasChildren && !row.expanded) toggle(row.node.key, true);
        else if (row.hasChildren) focusRow(rows[position + 1]?.node.key ?? null);
      },
      ArrowLeft: () => {
        if (row.hasChildren && row.expanded && !q) toggle(row.node.key, false);
        else focusRow(row.parent);
      },
      Enter: () => activate(row),
      ' ': () => activate(row)
    };
    const action = keyActions[event.key];
    if (!action) return;
    event.preventDefault();
    action();
  }
</script>

<aside class="b2s-list-pane" aria-label={ariaLabel}>
  <div class="b2s-list-pane__head">
    <div class="b2s-list-pane__searchrow">
      <SearchField
        wrapperClass="b2s-list-pane__search"
        placeholder={searchPlaceholder}
        ariaLabel={searchAriaLabel}
        value={query}
        onChange={(value) => onQueryChange(value)}
      />
      {#if onAdd}
        <button type="button" class="b2s-btn b2s-btn-primary b2s-list-pane__add" title={addLabel} aria-label={addLabel} on:click={() => onAdd?.()}>
          <i class="bi bi-plus-lg" aria-hidden="true"></i>
        </button>
      {/if}
    </div>
    {#if filters.length > 0}
      <div class="b2s-list-pane__filters" role="group" aria-label={t('Quick filters')}>
        {#each filters as filter (filter.key)}
          <button
            type="button"
            class="b2s-list-pane__filter"
            class:is-active={filter.key === activeFilter}
            aria-pressed={filter.key === activeFilter}
            on:click={() => onFilter(filter.key)}
          >
            {filter.label}
            {#if filter.count !== undefined}<span>{filter.count}</span>{/if}
          </button>
        {/each}
      </div>
    {/if}
    {#if viewMode || isTree}
      <div class="b2s-list-pane__tools">
        {#if viewMode}
          <div class="b2s-list-pane__views" role="group" aria-label={t('Display')}>
            <button type="button" class:is-active={viewMode === 'tree'} aria-pressed={viewMode === 'tree'} on:click={() => onViewMode('tree')}>
              <i class="bi bi-diagram-3" aria-hidden="true"></i>{t('Tree')}
            </button>
            <button type="button" class:is-active={viewMode === 'list'} aria-pressed={viewMode === 'list'} on:click={() => onViewMode('list')}>
              <i class="bi bi-list-ul" aria-hidden="true"></i>{t('List')}
            </button>
          </div>
        {/if}
        {#if isTree}
          <div class="b2s-list-pane__actions">
            <button type="button" title={t('Expand all')} aria-label={t('Expand all')} on:click={expandAll} disabled={Boolean(q)}>
              <i class="bi bi-arrows-expand" aria-hidden="true"></i>
            </button>
            <button type="button" title={t('Collapse all')} aria-label={t('Collapse all')} on:click={collapseAll} disabled={Boolean(q)}>
              <i class="bi bi-arrows-collapse" aria-hidden="true"></i>
            </button>
            <button type="button" title={t('Reveal selection')} aria-label={t('Reveal selection')} on:click={revealSelection} disabled={!index.selectedKey}>
              <i class="bi bi-crosshair" aria-hidden="true"></i>
            </button>
          </div>
        {/if}
      </div>
    {/if}
  </div>

  <div class="b2s-list-pane__body">
    {#if rows.length === 0}
      <div class="b2s-list-pane__empty" role="status" aria-live="polite">{emptyLabel}</div>
    {:else}
      <div class="b2s-tree" role="tree" tabindex="-1" aria-label={ariaLabel} bind:this={treeEl}>
        {#each rows as row (row.node.key)}
          {@const node = row.node}
          {@const active = node.selectId != null && String(node.selectId) === String(selectedId)}
          <div
            class="b2s-tree__row"
            class:is-active={active}
            class:is-muted={node.muted}
            class:is-top={row.depth === 0 && isTree}
            class:has-sub={Boolean(node.subtitle)}
            role="treeitem"
            aria-level={row.depth + 1}
            aria-expanded={row.hasChildren ? row.expanded : undefined}
            aria-selected={active}
            tabindex={node.key === focusedKey ? 0 : -1}
            title={node.title ?? undefined}
            data-key={node.key}
            on:click={() => activate(row)}
            on:keydown={onKeydown}
            on:focus={() => (focusedKey = node.key)}
          >
            {#each Array(row.depth) as _}<span class="b2s-tree__guide" aria-hidden="true"></span>{/each}
            {#if isTree}
              {#if row.hasChildren}
                <button
                  type="button"
                  class="b2s-tree__twisty"
                  tabindex="-1"
                  aria-label={row.expanded ? t('Collapse') : t('Expand')}
                  disabled={Boolean(q)}
                  on:click|stopPropagation={() => toggle(node.key)}
                >
                  <i class={`bi ${row.expanded ? 'bi-chevron-down' : 'bi-chevron-right'}`} aria-hidden="true"></i>
                </button>
              {:else}
                <span class="b2s-tree__twisty" aria-hidden="true"></span>
              {/if}
            {/if}
            {#if node.icon}
              <i class={`bi ${node.icon} b2s-tree__icon is-${node.iconTone ?? 'neutral'}`} aria-hidden="true"></i>
            {/if}
            <span class="b2s-tree__text">
              <span class="b2s-tree__label">
                {#each highlight(node.label) as part}{#if part.hit}<mark>{part.text}</mark>{:else}{part.text}{/if}{/each}
                {#if node.hint}<small>{node.hint}</small>{/if}
              </span>
              {#if node.subtitle}<span class="b2s-tree__sub">{node.subtitle}</span>{/if}
            </span>
            {#each [...(node.badges ?? []), ...(row.hasChildren && !row.expanded ? node.collapsedBadges ?? [] : [])] as badge}
              <span class={`b2s-tree__badge is-${badge.tone ?? 'neutral'}`} title={badge.title ?? undefined}>
                {#if badge.icon}<i class={`bi ${badge.icon}`} aria-hidden="true"></i>{/if}{badge.label}
              </span>
            {/each}
            {#if node.dot}<span class={`b2s-tree__dot is-${node.dot}`} aria-hidden="true"></span>{/if}
          </div>
        {/each}
      </div>
    {/if}
  </div>
</aside>

<style>
  .b2s-list-pane {
    position: sticky;
    top: 86px;
    display: flex;
    flex-direction: column;
    max-height: calc(100vh - 110px);
    min-width: 0;
    overflow: hidden;
    border: 1px solid var(--b2s-color-border-soft);
    border-radius: var(--b2s-radius-lg);
    background: var(--b2s-color-surface);
    box-shadow: 0 3px 10px rgba(18, 31, 64, 0.04);
  }

  .b2s-list-pane__head {
    display: grid;
    gap: 10px;
    padding: 16px 16px 8px;
  }

  .b2s-list-pane__searchrow {
    display: flex;
    gap: 8px;
  }

  .b2s-list-pane__searchrow :global(.b2s-list-pane__search) {
    flex: 1 1 auto;
    min-width: 0;
  }

  .b2s-list-pane__add {
    flex: none;
    width: 40px;
    height: 40px;
    padding: 0;
    justify-content: center;
  }

  .b2s-list-pane__head :global(.b2s-list-pane__search) {
    height: 40px;
    padding: 0 12px;
    border-radius: var(--b2s-radius-sm);
  }

  .b2s-list-pane__head :global(.b2s-list-pane__search input) {
    width: 100%;
    border: none;
    outline: none;
    background: transparent;
    font-size: var(--b2s-fs-sm);
  }

  .b2s-list-pane__filters {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .b2s-list-pane__filter {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    height: 26px;
    padding: 0 10px;
    border: 1px solid var(--b2s-color-border-soft);
    border-radius: var(--b2s-radius-pill);
    background: var(--b2s-color-surface);
    color: var(--b2s-color-text-soft);
    font-size: var(--b2s-fs-xs);
    cursor: pointer;
  }

  .b2s-list-pane__filter span {
    opacity: 0.75;
  }

  .b2s-list-pane__filter.is-active {
    border-color: var(--b2s-topbar-bg);
    background: var(--b2s-topbar-bg);
    color: #fff;
  }

  .b2s-list-pane__tools {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }

  .b2s-list-pane__views {
    display: inline-flex;
    gap: 2px;
    padding: 3px;
    border-radius: 9px;
    background: var(--b2s-color-neutral-soft);
  }

  .b2s-list-pane__views button {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 3px 10px;
    border: none;
    border-radius: 7px;
    background: transparent;
    color: var(--b2s-color-text-soft);
    font-size: var(--b2s-fs-xs);
    cursor: pointer;
  }

  .b2s-list-pane__views button.is-active {
    background: var(--b2s-color-surface);
    color: var(--b2s-color-text);
    font-weight: 600;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.12);
  }

  .b2s-list-pane__actions {
    display: inline-flex;
    gap: 2px;
    margin-left: auto;
  }

  .b2s-list-pane__actions button {
    width: 28px;
    height: 28px;
    display: grid;
    place-items: center;
    border: none;
    border-radius: 7px;
    background: transparent;
    color: var(--b2s-color-text-muted);
    cursor: pointer;
  }

  .b2s-list-pane__actions button:hover:not(:disabled) {
    background: var(--b2s-color-neutral-soft);
    color: var(--b2s-color-text);
  }

  .b2s-list-pane__actions button:disabled {
    opacity: 0.4;
    cursor: default;
  }

  .b2s-list-pane__body {
    flex: 1 1 auto;
    min-height: 0;
    overflow: auto;
    padding: 0 8px 12px;
  }

  .b2s-list-pane__empty {
    padding: 24px 16px;
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-sm);
    text-align: center;
  }

  .b2s-tree {
    display: flex;
    flex-direction: column;
    outline: none;
  }

  .b2s-tree__row {
    display: flex;
    align-items: center;
    gap: 6px;
    min-height: 32px;
    padding: 0 8px 0 4px;
    border-radius: 8px;
    color: var(--b2s-color-text);
    font-size: var(--b2s-fs-sm);
    cursor: pointer;
    user-select: none;
  }

  .b2s-tree__row.has-sub {
    min-height: 46px;
  }

  .b2s-tree__row:hover {
    background: #f5f8fc;
  }

  .b2s-tree__row:focus-visible {
    outline: 2px solid #93c5fd;
    outline-offset: -2px;
  }

  .b2s-tree__row.is-active {
    background: #e8efff;
    box-shadow: inset 3px 0 0 var(--b2s-topbar-bg);
  }

  .b2s-tree__row.is-active .b2s-tree__label {
    font-weight: 600;
  }

  .b2s-tree__row.is-top .b2s-tree__label {
    font-weight: 600;
  }

  .b2s-tree__row.is-muted .b2s-tree__label {
    color: var(--b2s-color-text-faint);
    font-style: italic;
  }

  .b2s-tree__guide {
    flex: 0 0 auto;
    align-self: stretch;
    width: 10px;
    margin-left: 9px;
    border-left: 1px solid var(--b2s-color-border-soft);
  }

  .b2s-tree__twisty {
    width: 18px;
    height: 18px;
    flex: 0 0 18px;
    display: grid;
    place-items: center;
    padding: 0;
    border: none;
    border-radius: 4px;
    background: transparent;
    color: var(--b2s-color-text-faint);
    font-size: 11px;
    cursor: pointer;
  }

  button.b2s-tree__twisty:hover:not(:disabled) {
    background: var(--b2s-color-border-soft);
    color: var(--b2s-color-text);
  }

  button.b2s-tree__twisty:disabled {
    cursor: inherit;
  }

  .b2s-tree__icon {
    flex: 0 0 auto;
    font-size: 15px;
    color: var(--b2s-color-text-muted);
  }

  .b2s-tree__icon.is-zone { color: #6366f1; }
  .b2s-tree__icon.is-server { color: #0ea5e9; }
  .b2s-tree__icon.is-folder { color: var(--b2s-color-border-mid); }
  .b2s-tree__icon.is-root { color: #d4a017; }

  .b2s-tree__text {
    flex: 1 1 auto;
    min-width: 0;
    display: flex;
    flex-direction: column;
  }

  .b2s-tree__label,
  .b2s-tree__sub {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .b2s-tree__label small {
    margin-left: 6px;
    color: var(--b2s-color-text-faint);
    font-size: 11.5px;
    font-weight: 400;
    font-style: normal;
  }

  .b2s-tree__label mark {
    padding: 0 1px;
    border-radius: 3px;
    background: #fef08a;
    color: inherit;
  }

  .b2s-tree__sub {
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-xs);
  }

  .b2s-tree__badge {
    flex: 0 0 auto;
    display: inline-flex;
    align-items: center;
    gap: 3px;
    min-width: 20px;
    justify-content: center;
    padding: 1px 7px;
    border-radius: var(--b2s-radius-pill);
    background: var(--b2s-color-neutral-soft);
    color: var(--b2s-color-text-muted);
    font-size: 11px;
    font-weight: 500;
  }

  .b2s-tree__badge.is-warning { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); font-weight: 600; }
  .b2s-tree__badge.is-error { background: var(--b2s-color-danger-soft); color: var(--b2s-color-danger-strong); font-weight: 600; }
  .b2s-tree__badge.is-info { background: var(--b2s-color-info-soft); color: var(--b2s-color-info-strong); font-weight: 600; }
  .b2s-tree__badge.is-error-quiet,
  .b2s-tree__badge.is-warning-quiet { background: transparent; color: var(--b2s-color-text-muted); }
  .b2s-tree__badge.is-error-quiet i { color: var(--b2s-color-danger); }
  .b2s-tree__badge.is-warning-quiet i { color: var(--b2s-color-warning); }

  .b2s-tree__dot {
    width: 8px;
    height: 8px;
    flex: 0 0 auto;
    border-radius: var(--b2s-radius-pill);
    background: var(--b2s-color-success);
  }

  .b2s-tree__dot.is-warning { background: #ea580c; }
  .b2s-tree__dot.is-error { background: var(--b2s-color-danger); }
  .b2s-tree__dot.is-neutral { background: var(--b2s-color-text-faint); }
</style>
