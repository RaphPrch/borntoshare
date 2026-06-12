<script lang="ts">
  import { createEventDispatcher } from 'svelte';

  export type DataTableColumn = {
    key: string;
    label: string;
    className?: string;
    sortable?: boolean;
  };

  export let columns: DataTableColumn[] = [];
  export let rows: Record<string, unknown>[] = [];
  export let clickableRows = false;
  export let selectedRowId: string | number | null = null;
  export let loading = false;
  export let loadingRows = 5;
  export let emptyLabel = 'No data';
  export let stickyHeader = false;
  export let density: 'standard' | 'compact' = 'standard';
  export let sortBy: string | null = null;
  export let sortDirection: 'asc' | 'desc' = 'asc';
  export let getRowId: ((row: Record<string, unknown>, index: number) => string | number) | null = null;

  let internalSortBy: string | null = sortBy;
  let internalSortDirection: 'asc' | 'desc' = sortDirection;

  $: if (sortBy !== null) {
    internalSortBy = sortBy;
  }
  $: if (sortDirection) {
    internalSortDirection = sortDirection;
  }

  const columnIsSortable = (key: string) =>
    columns.some((col) => col.key === key && col.sortable === true);

  const compareValues = (a: unknown, b: unknown) => {
    if (typeof a === 'number' && typeof b === 'number') return a - b;
    return String(a ?? '').localeCompare(String(b ?? ''), undefined, {
      sensitivity: 'base',
      numeric: true
    });
  };

  $: displayedRows = (() => {
    const source = Array.isArray(rows) ? [...rows] : [];
    if (!internalSortBy || !columnIsSortable(internalSortBy)) return source;
    source.sort((left, right) => {
      const vLeft = left?.[internalSortBy];
      const vRight = right?.[internalSortBy];
      const base = compareValues(vLeft, vRight);
      return internalSortDirection === 'asc' ? base : -base;
    });
    return source;
  })();

  const dispatch = createEventDispatcher<{
    rowclick: { row: Record<string, unknown>; index: number };
    sortchange: { key: string; direction: 'asc' | 'desc' };
  }>();

  const resolveRowId = (row: Record<string, unknown>, index: number) => {
    if (getRowId) return getRowId(row, index);
    const raw = row?.id;
    if (raw !== null && raw !== undefined && String(raw).trim() !== '') return String(raw);
    return `${index}`;
  };

  const handleSort = (key: string) => {
    if (!columnIsSortable(key)) return;
    if (internalSortBy === key) {
      internalSortDirection = internalSortDirection === 'asc' ? 'desc' : 'asc';
    } else {
      internalSortBy = key;
      internalSortDirection = 'asc';
    }
    dispatch('sortchange', { key: internalSortBy, direction: internalSortDirection });
  };
</script>

<div class={`b2s-table-wrap ${stickyHeader ? 'is-sticky' : ''}`}>
  <table class={`b2s-table ${density === 'compact' ? 'is-compact' : ''}`}>
    <thead>
      <tr>
        {#each columns as column (column.key)}
          <th class={`${column.className ?? ''} ${column.sortable ? 'is-sortable' : ''}`.trim()}>
            {#if column.sortable}
              <button
                type="button"
                class="b2s-table__sort-btn"
                on:click={() => handleSort(column.key)}
              >
                <span>{column.label}</span>
                {#if internalSortBy === column.key}
                  <i
                    class={`bi ${internalSortDirection === 'asc' ? 'bi-chevron-up' : 'bi-chevron-down'}`}
                    aria-hidden="true"
                  ></i>
                {/if}
              </button>
            {:else}
              {column.label}
            {/if}
          </th>
        {/each}
      </tr>
    </thead>
    <tbody>
      {#if loading}
        {#each Array(Math.max(1, loadingRows)) as _, index (`loading-${index}`)}
          <tr>
            <td colspan={Math.max(columns.length, 1)}>
              <div class="b2s-table__loading-line" aria-hidden="true"></div>
            </td>
          </tr>
        {/each}
      {:else if displayedRows.length === 0}
        <tr>
          <td colspan={Math.max(columns.length, 1)} class="b2s-table__empty">
            {emptyLabel}
          </td>
        </tr>
      {:else}
        {#each displayedRows as row, index (`${resolveRowId(row, index)}`)}
          <tr
            class:b2s-table__row--clickable={clickableRows}
            class:b2s-table__row--selected={selectedRowId !== null && String(resolveRowId(row, index)) === String(selectedRowId)}
            on:click={() => {
              if (!clickableRows) return;
              dispatch('rowclick', { row, index });
            }}
          >
            {#each columns as column (column.key)}
              <td class={column.className}>
                <slot name="cell" {row} {column}>
                  {String(row?.[column.key] ?? "-")}
                </slot>
              </td>
            {/each}
          </tr>
        {/each}
      {/if}
    </tbody>
  </table>
</div>

<style>
  .b2s-table__row--clickable {
    cursor: pointer;
  }

  .b2s-table__row--selected {
    background: rgba(59, 130, 246, 0.08);
  }

  .b2s-table__sort-btn {
    appearance: none;
    border: none;
    background: transparent;
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0;
    color: inherit;
    font: inherit;
    font-weight: inherit;
    cursor: pointer;
  }

  .b2s-table__loading-line {
    height: 14px;
    border-radius: 999px;
    background: linear-gradient(
      90deg,
      rgba(148, 163, 184, 0.24) 0%,
      rgba(148, 163, 184, 0.45) 50%,
      rgba(148, 163, 184, 0.24) 100%
    );
    background-size: 200% 100%;
    animation: b2s-table-loading 1.4s ease-in-out infinite;
  }

  @keyframes b2s-table-loading {
    0% {
      background-position: 200% 0;
    }
    100% {
      background-position: -200% 0;
    }
  }
</style>
