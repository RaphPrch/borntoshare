<script module lang="ts">
  export type EntitySidebarItem = {
    id: string | number;
    label: string;
    /** Second line under the name (path, host, code…) */
    subtitle?: string | null;
    /** @deprecated use subtitle */
    secondary?: string | null;
    icon?: string | null;
    /** Nesting level inside its group (0 = top level) */
    depth?: number;
    tone?: 'healthy' | 'warning' | 'error' | 'neutral';
    indicator?: { kind: 'pending' | 'warning' | 'error'; label: string } | null;
    raw?: unknown;
  };

  export type EntitySidebarGroup = {
    id: string | number;
    label: string;
    count?: number;
    warningCount?: number;
    items: EntitySidebarItem[];
  };

  export type EntitySidebarFilter = { key: string; label: string; count?: number };
</script>

<script lang="ts">
  import { t } from '$lib/i18n';
  import SearchField from '$lib/components/ui/SearchField.svelte';

  /**
   * List pane of the entity workspaces (zones, storage endpoints, storage roots):
   * search, quick filters, collapsible groups and selectable rows.
   */
  export let ariaLabel = t('Entity list');
  export let searchPlaceholder = t('Search');
  export let searchAriaLabel = t('Search');
  export let emptyLabel = t('No item matches your search.');
  export let query = '';
  export let groups: EntitySidebarGroup[] = [];
  export let selectedId: string | number | null = null;
  export let grouped = true;
  export let showToneDot = true;
  export let itemIcon = 'bi-circle';
  export let filters: EntitySidebarFilter[] = [];
  export let activeFilter = '';
  export let onFilter: (key: string) => void = () => {};
  export let isOpenGroup: (groupId: string | number) => boolean = () => true;
  export let onToggleGroup: (groupId: string | number) => void = () => {};
  export let onSelect: (id: string | number, item: EntitySidebarItem) => void = () => {};
  export let onQueryChange: (value: string) => void = () => {};

  const itemId = (item: EntitySidebarItem): string => String(item.id);
  $: flatItems = groups.flatMap((group) => group.items ?? []);
</script>

<aside class="b2s-list-pane" aria-label={ariaLabel}>
  <div class="b2s-list-pane__head">
    <SearchField
      wrapperClass="b2s-list-pane__search"
      placeholder={searchPlaceholder}
      ariaLabel={searchAriaLabel}
      value={query}
      onChange={(value) => onQueryChange(value)}
    />
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
  </div>

  <div class="b2s-list-pane__body">
    {#if flatItems.length === 0}
      <div class="b2s-list-pane__empty" role="status" aria-live="polite">{emptyLabel}</div>
    {:else}
      {#each grouped ? groups : [{ id: '__all', label: '', items: flatItems }] as group (String(group.id))}
        {@const open = !grouped || isOpenGroup(group.id)}
        {#if grouped}
          <button
            type="button"
            class="b2s-list-pane__group"
            on:click={() => onToggleGroup(group.id)}
            aria-expanded={open}
          >
            <i class={`bi ${open ? 'bi-chevron-down' : 'bi-chevron-right'}`} aria-hidden="true"></i>
            <span class="b2s-list-pane__group-label">{group.label}</span>
            {#if Number(group.warningCount ?? 0) > 0}
              <span class="b2s-list-pane__group-alerts" title={t('{count} alerts', { count: Number(group.warningCount) })}>
                <i class="bi bi-exclamation-triangle-fill" aria-hidden="true"></i>{group.warningCount}
              </span>
            {/if}
            <span class="b2s-list-pane__group-count">{group.count ?? group.items.length}</span>
          </button>
        {/if}
        {#if open}
          <ul class="b2s-list-pane__list">
            {#each group.items as item (itemId(item))}
              {@const active = String(item.id) === String(selectedId)}
              <li>
                <button
                  type="button"
                  class="b2s-list-pane__item"
                  class:is-active={active}
                  style={`--depth:${Math.min(4, Number(item.depth ?? 0))}`}
                  on:click={() => onSelect(item.id, item)}
                  aria-current={active ? 'page' : undefined}
                >
                  <span class="b2s-list-pane__icon" aria-hidden="true"><i class={`bi ${item.icon ?? itemIcon}`}></i></span>
                  <span class="b2s-list-pane__text">
                    <span class="b2s-list-pane__name">{item.label}</span>
                    {#if item.subtitle ?? item.secondary}
                      <span class="b2s-list-pane__sub">{item.subtitle ?? item.secondary}</span>
                    {/if}
                  </span>
                  {#if item.indicator}
                    <span class={`b2s-list-pane__count is-${item.indicator.kind}`} title={item.indicator.label}>
                      {item.indicator.label.replace(/\D+/g, '') || '!'}
                    </span>
                  {:else if showToneDot}
                    <span class={`b2s-list-pane__dot is-${item.tone ?? 'healthy'}`} aria-hidden="true"></span>
                  {/if}
                </button>
              </li>
            {/each}
          </ul>
        {/if}
      {/each}
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
    border: 1px solid #e5eaf3;
    border-radius: var(--b2s-radius-lg);
    background: var(--b2s-color-surface);
    box-shadow: 0 3px 10px rgba(18, 31, 64, 0.04);
  }

  .b2s-list-pane__head {
    display: grid;
    gap: 10px;
    padding: 16px 16px 8px;
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
    border: 1px solid #e5eaf3;
    border-radius: var(--b2s-radius-pill);
    background: var(--b2s-color-surface);
    color: #475569;
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

  .b2s-list-pane__body {
    flex: 1 1 auto;
    min-height: 0;
    overflow: auto;
    padding: 0 0 12px;
  }

  .b2s-list-pane__empty {
    padding: 24px 16px;
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-sm);
    text-align: center;
  }

  .b2s-list-pane__group {
    width: 100%;
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 12px 16px 4px;
    border: none;
    background: transparent;
    color: #64748b;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    text-align: left;
    cursor: pointer;
  }

  .b2s-list-pane__group-label {
    flex: 1 1 auto;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .b2s-list-pane__group-alerts {
    display: inline-flex;
    align-items: center;
    gap: 3px;
    color: #c2410c;
    letter-spacing: 0;
  }

  .b2s-list-pane__group-count {
    letter-spacing: 0;
  }

  .b2s-list-pane__list {
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .b2s-list-pane__item {
    width: calc(100% - 16px);
    margin: 2px 8px;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 7px 10px 7px calc(10px + var(--depth, 0) * 16px);
    border: none;
    border-radius: 10px;
    background: transparent;
    color: var(--b2s-color-text);
    text-align: left;
    cursor: pointer;
  }

  .b2s-list-pane__item:hover {
    background: #f5f8fc;
  }

  .b2s-list-pane__item.is-active {
    background: #eef4ff;
    box-shadow: inset 3px 0 0 var(--b2s-topbar-bg);
  }

  .b2s-list-pane__icon {
    width: 30px;
    height: 30px;
    flex: 0 0 auto;
    display: grid;
    place-items: center;
    border-radius: 8px;
    background: #f1f5f9;
    color: #475569;
  }

  .b2s-list-pane__item.is-active .b2s-list-pane__icon {
    background: #dbe7ff;
    color: var(--b2s-topbar-bg);
  }

  .b2s-list-pane__text {
    flex: 1 1 auto;
    min-width: 0;
    display: flex;
    flex-direction: column;
  }

  .b2s-list-pane__name,
  .b2s-list-pane__sub {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .b2s-list-pane__name {
    font-size: var(--b2s-fs-md);
    font-weight: 500;
  }

  .b2s-list-pane__sub {
    color: #64748b;
    font-size: var(--b2s-fs-xs);
  }

  .b2s-list-pane__dot {
    width: 8px;
    height: 8px;
    flex: 0 0 auto;
    border-radius: var(--b2s-radius-pill);
    background: #16a34a;
  }

  .b2s-list-pane__dot.is-warning { background: #ea580c; }
  .b2s-list-pane__dot.is-error { background: #dc2626; }
  .b2s-list-pane__dot.is-neutral { background: #94a3b8; }

  .b2s-list-pane__count {
    flex: 0 0 auto;
    min-width: 20px;
    padding: 1px 7px;
    border-radius: var(--b2s-radius-pill);
    background: #fff4e5;
    color: #c2410c;
    font-size: 11px;
    font-weight: 600;
    text-align: center;
  }

  .b2s-list-pane__count.is-error {
    background: #fdecec;
    color: #b91c1c;
  }

  .b2s-list-pane__count.is-pending {
    background: #eaf2ff;
    color: #1d4ed8;
  }
</style>
