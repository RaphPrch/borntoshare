<script lang="ts">
  import EmptyStateInline from '$lib/components/ui/EmptyStateInline.svelte';
  import StatusBadge from '$lib/components/ui/StatusBadge.svelte';
  // Tones of the states, as StatusBadge variants
  const TONE_VARIANT: Record<string, 'success' | 'warning' | 'error' | 'muted'> = { ok: 'success', warn: 'warning', bad: 'error', n: 'muted' };
  import SegmentedFilter from '$lib/components/ui/SegmentedFilter.svelte';
  import { t } from '$lib/i18n';

  /** Folders governed on a server: hundreds of them stay readable (search, filters, compact rows, by page). */
  type Row = { id: number; name: string; path: string; pendingCount: number | null; health?: string | null; alertCount?: number };
  export let rows: Row[] = [];
  /** \\host\ shown once in the page header: the rows show the path inside the server */
  export let host = '';

  const PAGE = 50;
  let query = '';
  let filter: 'all' | 'todo' | 'down' | 'pending' = 'all';
  let shown = PAGE;

  // Where the folder is, under the server (named once in the header) and without its own name again
  const inside = (row: Row) => {
    let parts = row.path.split(/[\\/]+/).filter(Boolean);
    if (parts.length && host && parts[0].toLowerCase() === host.toLowerCase()) parts = parts.slice(1);
    if (parts.length && parts[parts.length - 1].toLowerCase() === row.name.toLowerCase()) parts = parts.slice(0, -1);
    return parts.length ? `${parts.join('\\')}\\` : '';
  };
  const down = (row: Row) => row.health === 'unhealthy';
  const todo = (row: Row) => down(row) || Boolean(row.alertCount) || row.health === 'degraded';
  const state = (row: Row) =>
    down(row) ? { label: t('Unreachable'), tone: 'bad' }
    : row.alertCount ? { label: t('{count} alert(s)', { count: row.alertCount }), tone: 'warn' }
    : row.health === 'healthy' ? { label: t('OK'), tone: 'ok' }
    : { label: t('To verify'), tone: 'n' };

  $: counts = { all: rows.length, todo: rows.filter(todo).length, down: rows.filter(down).length, pending: rows.filter((row) => (row.pendingCount ?? 0) > 0).length };
  $: matching = rows
    .filter((row) => filter === 'all' || (filter === 'todo' ? todo(row) : filter === 'down' ? down(row) : (row.pendingCount ?? 0) > 0))
    .filter((row) => `${row.name} ${row.path}`.toLowerCase().includes(query.trim().toLowerCase()))
    .sort((a, b) => Number(todo(b)) - Number(todo(a)) || a.name.localeCompare(b.name, 'fr', { numeric: true }));
  $: if (query || filter) shown = PAGE;
</script>

<div class="tools">
  <input class="b2s-input" aria-label={t('Filter the folders')} placeholder={t('Filter the folders…')} bind:value={query} />
  <SegmentedFilter ariaLabel={t('Filter by state')} bind:value={filter} options={[
    { key: 'all', label: t('All'), count: counts.all },
    { key: 'todo', label: t('To review'), count: counts.todo },
    { key: 'down', label: t('Unreachable'), count: counts.down },
    { key: 'pending', label: t('Pending requests'), count: counts.pending }
  ]} />
</div>

{#if matching.length}
  <ul class="list">
    {#each matching.slice(0, shown) as row (row.id)}
      {@const s = state(row)}
      <li>
        <a href={`/storage-roots?selected=${row.id}`}>
          <span class="name"><strong>{row.name}</strong><small>{inside(row)}</small></span>
          <StatusBadge compact variant={TONE_VARIANT[s.tone]} label={s.label} />
          <span class="req">{(row.pendingCount ?? 0) > 0 ? t('{count} request(s)', { count: row.pendingCount }) : ''}</span>
        </a>
      </li>
    {/each}
  </ul>
  {#if matching.length > shown}
    <button type="button" class="more" on:click={() => (shown += PAGE)}>{t('Show {count} more ({total} left)', { count: Math.min(PAGE, matching.length - shown), total: matching.length - shown })}</button>
  {/if}
{:else}
  <EmptyStateInline message={rows.length ? t('No folder matches this search.') : t('No folder managed on this server yet.')} />
{/if}

<style>
  .tools { display: flex; gap: 8px; align-items: center; margin-bottom: 10px; }
  .tools .b2s-input { flex: 1; min-width: 0; }
  .list { margin: 0; padding: 0; list-style: none; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-md); background: var(--b2s-color-surface); }
  .list li + li { border-top: 1px solid var(--b2s-color-border); }
  .list a { display: grid; grid-template-columns: minmax(0, 1fr) 110px 92px; gap: 12px; align-items: center; padding: 7px 12px; color: inherit; text-decoration: none; }
  .list a:hover { background: var(--b2s-color-surface-soft); }
  .name { display: flex; align-items: baseline; gap: 10px; min-width: 0; }
  .name strong { font-weight: 500; white-space: nowrap; }
  .name small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--b2s-color-text-muted); font-family: var(--b2s-font-mono); font-size: var(--b2s-font-micro); }
  .req { color: var(--b2s-color-warning-strong); font-size: var(--b2s-font-micro); text-align: right; }
  .more { width: 100%; margin-top: 8px; padding: 8px; border: 1px dashed var(--b2s-color-border-mid); border-radius: var(--b2s-radius-md); background: none; color: var(--b2s-color-text-muted); cursor: pointer; }
</style>
