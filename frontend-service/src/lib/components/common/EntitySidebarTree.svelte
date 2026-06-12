<script lang="ts">
  import EntityActionButton from '$lib/components/common/EntityActionButton.svelte';
  import SearchField from '$lib/components/common/SearchField.svelte';

  export type EntitySidebarItem = {
    id: string | number;
    label: string;
    secondary?: string | null;
    tone?: 'healthy' | 'warning' | 'error';
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

  export let ariaLabel = 'Entity sidebar';
  export let createLabel = 'New item';
  export let searchPlaceholder = 'Search';
  export let searchAriaLabel = 'Search';
  export let emptyLabel = 'No item matches your search.';
  export let query = '';
  export let groups: EntitySidebarGroup[] = [];
  export let selectedId: string | number | null = null;
  export let grouped = true;
  export let showToneDot = true;
  export let isOpenGroup: (groupId: string | number) => boolean = () => true;
  export let onToggleGroup: (groupId: string | number) => void = () => {};
  export let onSelect: (id: string | number, item: EntitySidebarItem) => void = () => {};
  export let onCreate: (() => void) | null = null;
  export let onQueryChange: (value: string) => void = () => {};

  const itemTone = (item: EntitySidebarItem): 'healthy' | 'warning' | 'error' => item.tone ?? 'healthy';
  const itemId = (item: EntitySidebarItem): string => String(item.id);
  $: flatItems = groups.flatMap((group) => group.items ?? []);
</script>

<aside class="b2s-entity-sidebar" aria-label={ariaLabel}>
  {#if onCreate}
    <EntityActionButton
      compact={true}
      variant="primary"
      icon="bi-plus-lg"
      label={createLabel}
      className="b2s-entity-sidebar__create"
      onClick={() => onCreate?.()}
    />
  {/if}

  <SearchField
    wrapperClass="b2s-entity-sidebar__search"
    inputClass="b2s-entity-sidebar__search-input"
    placeholder={searchPlaceholder}
    ariaLabel={searchAriaLabel}
    value={query}
    onChange={(value) => onQueryChange(value)}
  />

  <div class="b2s-entity-tree">
    {#if groups.length === 0 || flatItems.length === 0}
      <div class="sr-clean-empty-inline" role="status" aria-live="polite">{emptyLabel}</div>
    {:else if grouped}
      {#each groups as group (String(group.id))}
        {@const open = isOpenGroup(group.id)}
        {@const warningCount = Number(group.warningCount ?? 0)}
        <section class="b2s-entity-tree__group">
          <button
            type="button"
            class="b2s-entity-tree__group-row"
            on:click={() => onToggleGroup(group.id)}
            aria-expanded={open}
            aria-label={`${group.label} (${group.count ?? group.items.length})`}
          >
            <i class={`bi ${open ? 'bi-caret-down-fill' : 'bi-caret-right-fill'}`}></i>
            <span class="b2s-entity-tree__group-title">{group.label}</span>
            <span class="b2s-entity-tree__group-trailing">
              {#if warningCount > 0}
                <span class="b2s-entity-tree__group-warning" title={`${warningCount} warning${warningCount > 1 ? 's' : ''}`}>
                  <i class="bi bi-exclamation-triangle-fill"></i>
                  {warningCount}
                </span>
              {/if}
              <span class="b2s-entity-tree__group-count">{group.count ?? group.items.length}</span>
            </span>
          </button>

          {#if open}
            <ul class="b2s-entity-tree__list">
              {#each group.items as item (itemId(item))}
                <li>
                  <button
                    type="button"
                    class={`b2s-entity-tree__item ${showToneDot ? '' : 'has-no-dot'} ${String(item.id) === String(selectedId) ? 'is-active' : ''}`}
                    on:click={() => onSelect(item.id, item)}
                    aria-current={String(item.id) === String(selectedId) ? 'page' : undefined}
                    aria-label={`Select ${item.label}`}
                  >
                    {#if showToneDot}
                      <span class={`b2s-entity-tree__dot is-${itemTone(item)}`}></span>
                    {/if}
                    <span class="b2s-entity-tree__item-name">{item.label}</span>
                    {#if item.secondary || item.indicator}
                      <span class="b2s-entity-tree__item-trailing">
                        {#if item.secondary}
                          <span class="b2s-entity-tree__secondary is-pending">{item.secondary}</span>
                        {/if}
                        {#if item.indicator}
                          <span class={`b2s-entity-tree__secondary is-${item.indicator.kind}`}>
                            {item.indicator.label}
                          </span>
                        {/if}
                      </span>
                    {/if}
                  </button>
                </li>
              {/each}
            </ul>
          {/if}
        </section>
      {/each}
    {:else}
      <ul class="b2s-entity-tree__list">
        {#each flatItems as item (itemId(item))}
          <li>
            <button
              type="button"
              class={`b2s-entity-tree__item ${showToneDot ? '' : 'has-no-dot'} ${String(item.id) === String(selectedId) ? 'is-active' : ''}`}
              on:click={() => onSelect(item.id, item)}
              aria-current={String(item.id) === String(selectedId) ? 'page' : undefined}
              aria-label={`Select ${item.label}`}
            >
              {#if showToneDot}
                <span class={`b2s-entity-tree__dot is-${itemTone(item)}`}></span>
              {/if}
              <span class="b2s-entity-tree__item-name">{item.label}</span>
              {#if item.secondary || item.indicator}
                <span class="b2s-entity-tree__item-trailing">
                  {#if item.secondary}
                    <span class="b2s-entity-tree__secondary is-pending">{item.secondary}</span>
                  {/if}
                  {#if item.indicator}
                    <span class={`b2s-entity-tree__secondary is-${item.indicator.kind}`}>
                      {item.indicator.label}
                    </span>
                  {/if}
                </span>
              {/if}
            </button>
          </li>
        {/each}
      </ul>
    {/if}
  </div>
</aside>

<style>
  .b2s-entity-sidebar {
    border-right: 0;
    background: var(--b2s-color-surface-soft, #f7f9fd);
    padding: 14px 12px;
    display: grid;
    grid-template-rows: auto auto minmax(0, 1fr);
    gap: 12px;
    width: 100%;
    min-width: 0;
    min-height: 0;
    height: 100%;
    overflow: hidden;
  }

  .b2s-entity-sidebar__create {
    width: 100%;
  }

  .b2s-entity-sidebar__search {
    height: 40px;
    border: 1px solid var(--b2s-color-border, #dbe2ef);
    border-radius: 10px;
    background: var(--b2s-color-surface, #fff);
    padding: 0 10px;
  }

  .b2s-entity-sidebar__search-input {
    font-size: 14px;
  }

  .b2s-entity-tree {
    overflow: auto;
    min-height: 0;
  }

  .b2s-entity-tree__group + .b2s-entity-tree__group {
    margin-top: 8px;
  }

  .b2s-entity-tree__group-row {
    width: 100%;
    border: none;
    background: transparent;
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 4px;
    color: #334b74;
  }

  .b2s-entity-tree__group-trailing {
    margin-left: auto;
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }

  .b2s-entity-tree__group-warning,
  .b2s-entity-tree__group-count,
  .b2s-entity-tree__secondary {
    border-radius: 999px;
    font-size: 11px;
    font-weight: 700;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }

  .b2s-entity-tree__group-warning {
    height: 22px;
    border: 1px solid #f2d8a7;
    background: var(--b2s-color-warning-soft, #fff6e8);
    color: #a86500;
    gap: 4px;
    padding: 0 8px;
  }

  .b2s-entity-tree__group-title {
    font-size: 13px;
    font-weight: 700;
  }

  .b2s-entity-tree__group-count {
    min-width: 22px;
    height: 22px;
    border: 1px solid var(--b2s-color-border, #d7dfef);
    background: #edf2fa;
    color: #425c8f;
    font-size: 12px;
    padding: 0 6px;
  }

  .b2s-entity-tree__list {
    list-style: none;
    margin: 4px 0 0;
    padding: 0;
    display: grid;
    gap: 4px;
  }

  .b2s-entity-tree__item {
    width: 100%;
    height: 40px;
    border: 1px solid transparent;
    border-radius: 10px;
    background: transparent;
    display: flex;
    align-items: center;
    justify-content: flex-start;
    gap: 8px;
    padding: 0 10px;
    color: #273b62;
    text-align: left;
  }

  .b2s-entity-tree__item.is-active {
    background: #e8f0ff;
    border-color: #d5e2fb;
    box-shadow: inset 3px 0 0 #2f6adf;
  }

  .b2s-entity-tree__item.has-no-dot {
    padding-left: 12px;
  }

  .b2s-entity-tree__item-name {
    min-width: 0;
    flex: 1;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    font-size: 14px;
    font-weight: 600;
    text-align: left;
  }

  .b2s-entity-tree__dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex: 0 0 auto;
  }

  .b2s-entity-tree__dot.is-healthy {
    color: #23a26d;
    background: #23a26d;
  }

  .b2s-entity-tree__dot.is-warning {
    color: #d59a2a;
    background: #d59a2a;
  }

  .b2s-entity-tree__dot.is-error {
    color: #e15b4f;
    background: #e15b4f;
  }

  .b2s-entity-tree__secondary {
    min-width: 18px;
    height: 18px;
    padding: 0 6px;
  }

  .b2s-entity-tree__item-trailing {
    margin-left: auto;
    display: inline-flex;
    align-items: center;
    justify-content: flex-end;
    gap: 6px;
    flex: 0 0 auto;
  }

  .b2s-entity-tree__secondary.is-pending {
    background: #edf2fa;
    color: #425c8f;
    border: 1px solid #d7dfef;
  }

  .b2s-entity-tree__secondary.is-warning {
    background: var(--b2s-color-warning-soft, #fff6e8);
    color: #a86500;
    border: 1px solid #f2d8a7;
  }

  .b2s-entity-tree__secondary.is-error {
    background: #ffecec;
    color: #b5473f;
    border: 1px solid #f5cbc8;
  }
</style>
