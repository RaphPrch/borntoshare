<script lang="ts">
  import { t } from '$lib/i18n';

  /** Total number of rows */
  export let total = 0;
  /** Current page, starting at 1 */
  export let page = 1;
  export let pageSize = 25;
  export let pageSizes: number[] = [10, 25, 50, 100];

  $: totalPages = Math.max(1, Math.ceil(total / pageSize));
  $: if (page > totalPages) page = totalPages;
  $: if (page < 1) page = 1;
  $: start = total === 0 ? 0 : (page - 1) * pageSize + 1;
  $: end = Math.min(total, page * pageSize);

  const go = (target: number) => {
    page = Math.min(Math.max(1, target), totalPages);
  };
</script>

<div class="b2s-pagination">
  <label class="b2s-pagination__size">
    {t('Rows per page:')}
    <select bind:value={pageSize} on:change={() => (page = 1)}>
      {#each pageSizes as size}
        <option value={size}>{size}</option>
      {/each}
    </select>
  </label>
  <div class="b2s-pagination__nav">
    <span>{t('{start}–{end} of {total}', { start, end, total })}</span>
    <button type="button" aria-label={t('First page')} disabled={page <= 1} on:click={() => go(1)}>
      <i class="bi bi-chevron-bar-left" aria-hidden="true"></i>
    </button>
    <button type="button" aria-label={t('Previous page')} disabled={page <= 1} on:click={() => go(page - 1)}>
      <i class="bi bi-chevron-left" aria-hidden="true"></i>
    </button>
    <strong>{page}</strong>
    <button type="button" aria-label={t('Next page')} disabled={page >= totalPages} on:click={() => go(page + 1)}>
      <i class="bi bi-chevron-right" aria-hidden="true"></i>
    </button>
    <button type="button" aria-label={t('Last page')} disabled={page >= totalPages} on:click={() => go(totalPages)}>
      <i class="bi bi-chevron-bar-right" aria-hidden="true"></i>
    </button>
  </div>
</div>

<style>
  .b2s-pagination {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    flex-wrap: wrap;
    padding: 12px 16px;
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-sm);
  }

  .b2s-pagination__size {
    display: inline-flex;
    align-items: center;
    gap: 8px;
  }

  .b2s-pagination__size select {
    height: 32px;
    padding: 0 8px;
    border: 1px solid var(--b2s-color-border);
    border-radius: var(--b2s-radius-sm);
    background: var(--b2s-color-surface);
    color: var(--b2s-color-text);
  }

  .b2s-pagination__nav {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }

  .b2s-pagination__nav span {
    margin-right: 6px;
  }

  .b2s-pagination__nav button {
    width: 32px;
    height: 32px;
    display: inline-grid;
    place-items: center;
    border: 1px solid var(--b2s-color-border);
    border-radius: var(--b2s-radius-sm);
    background: var(--b2s-color-surface);
    color: var(--b2s-color-text);
    cursor: pointer;
  }

  .b2s-pagination__nav button:disabled {
    opacity: 0.4;
    cursor: default;
  }

  .b2s-pagination__nav strong {
    min-width: 32px;
    height: 32px;
    display: inline-grid;
    place-items: center;
    border-radius: var(--b2s-radius-sm);
    background: var(--b2s-color-primary-strong);
    color: #fff;
  }
</style>
