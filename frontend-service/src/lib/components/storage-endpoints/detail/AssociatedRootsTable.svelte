<script lang="ts">
  type AssociatedRootRow = {
    id: number;
    name: string;
    path: string;
    pendingCount: number | null;
  };

  export let rows: AssociatedRootRow[] = [];
  export let dense = false;
  export let emptyLabel = 'No associated roots';

  const requestsToneClass = (pendingCount: number | null): string => {
    if (pendingCount === null) return 'is-muted';
    if (pendingCount > 0) return 'is-warning';
    return 'is-success';
  };
</script>

<div class={`sed-table-wrap ${dense ? 'is-dense' : ''}`}>
  <table class="sed-table">
    <thead>
      <tr>
        <th>Name</th>
        <th>Path</th>
        <th>Requests</th>
      </tr>
    </thead>
    <tbody>
      {#if rows.length === 0}
        <tr>
          <td colspan="3" class="sed-empty-row">{emptyLabel}</td>
        </tr>
      {:else}
        {#each rows as row (row.id)}
          <tr>
            <td class="sed-cell-strong">
              <a class="sed-root-link" href={`/storage-roots/${row.id}`}>
                <i class="bi bi-folder2"></i>
                {row.name}
              </a>
            </td>
            <td class="sed-cell-path">{row.path}</td>
            <td>
              {#if row.pendingCount === null}
                <span class="sed-neutral-pill is-muted">Unavailable</span>
              {:else}
                <span class={`sed-neutral-pill ${requestsToneClass(row.pendingCount)} ${row.pendingCount > 0 ? 'has-value' : ''}`}>
                  {row.pendingCount}
                </span>
              {/if}
            </td>
          </tr>
        {/each}
      {/if}
    </tbody>
  </table>
</div>

<style>
  .sed-cell-path {
    white-space: normal;
    overflow-wrap: anywhere;
    word-break: break-word;
  }

  .sed-cell-detail {
    min-width: 180px;
    color: #52627a;
    font-size: 12px;
    line-height: 1.35;
    white-space: normal;
  }
</style>
