<script lang="ts">
  import EmptyStateInline from '$lib/components/ui/EmptyStateInline.svelte';
  import StatusBadge from '$lib/components/ui/StatusBadge.svelte';
  import SegmentedFilter from '$lib/components/ui/SegmentedFilter.svelte';
  import { t } from '$lib/i18n';

  /**
   * Folders governed on a server, grouped by share: the folders that need something come first, the ones in order
   * are folded (« 10 in order · Show »), so that hundreds of folders stay readable.
   */
  type Row = { id: number; name: string; path: string; pendingCount: number | null; health?: string | null; alertCount?: number; guardians?: number };
  export let rows: Row[] = [];
  /** \\host\ shown once in the page header: the rows show the path inside the server */
  export let host = '';

  const TONE_VARIANT: Record<string, 'success' | 'warning' | 'error' | 'muted'> = { ok: 'success', warn: 'warning', bad: 'error', n: 'muted' };
  let query = '';
  let filter: 'all' | 'todo' | 'down' | 'pending' = 'all';
  let opened = new Set<string>();
  let calmShown = new Set<string>();

  const parts = (row: Row) => {
    let list = row.path.split(/[\\/]+/).filter(Boolean);
    if (list.length && host && list[0].toLowerCase() === host.toLowerCase()) list = list.slice(1);
    return list;
  };
  const shareOf = (row: Row) => parts(row)[0] ?? '—';
  // The path under the share, without the folder name again
  const inside = (row: Row) => {
    const list = parts(row).slice(1);
    if (list.length && list[list.length - 1].toLowerCase() === row.name.toLowerCase()) list.pop();
    return list.length ? `${list.join('\\')}\\` : '';
  };
  const down = (row: Row) => row.health === 'unhealthy';
  const todo = (row: Row) => down(row) || Boolean(row.alertCount) || row.health === 'degraded';
  const state = (row: Row) =>
    down(row) ? { label: t('Unreachable'), tone: 'bad' }
    : row.alertCount ? { label: t('{count} alert(s)', { count: row.alertCount }), tone: 'warn' }
    : row.health === 'healthy' ? null
    : { label: t('To verify'), tone: 'n' };

  $: counts = { all: rows.length, todo: rows.filter(todo).length, down: rows.filter(down).length, pending: rows.filter((row) => (row.pendingCount ?? 0) > 0).length };
  $: needle = query.trim().toLowerCase();
  $: matching = rows
    .filter((row) => filter === 'all' || (filter === 'todo' ? todo(row) : filter === 'down' ? down(row) : (row.pendingCount ?? 0) > 0))
    .filter((row) => !needle || `${row.name} ${row.path}`.toLowerCase().includes(needle));
  $: groups = [...new Set(matching.map(shareOf))]
    .map((share) => {
      const list = matching.filter((row) => shareOf(row) === share).sort((a, b) => a.name.localeCompare(b.name, 'fr', { numeric: true }));
      const hot = list.filter((row) => todo(row) || (row.pendingCount ?? 0) > 0);
      return { share, hot, calm: list.filter((row) => !hot.includes(row)), total: list.length };
    })
    .sort((a, b) => b.hot.length - a.hot.length || a.share.localeCompare(b.share, 'fr', { numeric: true }));
  // A share with something to do opens by itself; a search or a filter shows everything that matches
  const isOpen = (group: { share: string; hot: Row[] }, searching: boolean) => searching || group.hot.length > 0 || opened.has(group.share);
  function toggle(share: string) {
    if (opened.has(share)) opened.delete(share);
    else opened.add(share);
    opened = opened;
  }
  function showCalm(share: string) {
    calmShown.add(share);
    calmShown = calmShown;
  }
</script>

<div class="tools">
  <input class="b2s-input" aria-label={t('Filter the folders')} placeholder={t('Filter the {count} folders (name, path)', { count: rows.length })} bind:value={query} />
  <SegmentedFilter ariaLabel={t('Filter by state')} bind:value={filter} options={[
    { key: 'all', label: t('All'), count: counts.all },
    { key: 'todo', label: t('To review'), count: counts.todo },
    { key: 'down', label: t('Unreachable'), count: counts.down },
    { key: 'pending', label: t('Pending requests'), count: counts.pending }
  ]} />
</div>

{#if groups.length}
  <div class="groups">
    {#each groups as group (group.share)}
      {@const open = isOpen(group, Boolean(needle) || filter !== 'all')}
      <section class="share">
        <button type="button" class="share__head" aria-expanded={open} on:click={() => toggle(group.share)}>
          <span class="car" aria-hidden="true">{open ? '▾' : '▸'}</span>
          <code title={`\\\\${host}\\${group.share}`}>\\{host}\{group.share}</code>
          <span class="share__sum">
            {#if group.hot.length}<StatusBadge compact variant="warning" label={t('{count} to review', { count: group.hot.length })} />{/if}
            <small>{t('{count} folder(s)', { count: group.total })}</small>
          </span>
        </button>
        {#if open}
          <div class="row row--head" aria-hidden="true"><span>{t('Folder')}</span><span>{t('Guardians')}</span><span>{t('Requests')}</span><span>{t('State')}</span></div>
          {#each [...group.hot, ...(calmShown.has(group.share) || needle || filter !== 'all' ? group.calm : [])] as row (row.id)}
            {@const s = state(row)}
            <a class="row" href={`/storage-roots?selected=${row.id}`}>
              <span class="name"><strong>{row.name}</strong>{#if inside(row)}<small>{inside(row)}</small>{/if}</span>
              <span class="muted">{Number.isFinite(row.guardians) ? row.guardians : '—'}</span>
              <span>{#if (row.pendingCount ?? 0) > 0}<StatusBadge compact variant="warning" label={t('{count} pending', { count: row.pendingCount })} />{:else}<span class="muted">—</span>{/if}</span>
              <span>{#if s}<StatusBadge compact variant={TONE_VARIANT[s.tone]} label={s.label} />{:else}<span class="ok">✓ {t('in order')}</span>{/if}</span>
            </a>
          {/each}
          {#if group.calm.length && !(calmShown.has(group.share) || needle || filter !== 'all')}
            <div class="calm"><span>{t('{count} folder(s) in order', { count: group.calm.length })}</span><button type="button" class="b2s-link-btn" on:click={() => showCalm(group.share)}>{t('Show')}</button></div>
          {/if}
        {/if}
      </section>
    {/each}
  </div>
{:else}
  <EmptyStateInline message={rows.length ? t('No folder matches this search.') : t('No folder managed on this server yet.')} />
{/if}

<style>
  .tools { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }
  .tools .b2s-input { flex: 1; min-width: 0; }
  .groups { display: flex; flex-direction: column; gap: 8px; }
  .share { border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-md); background: var(--b2s-color-surface); overflow: hidden; }
  .share__head { display: flex; align-items: center; gap: 8px; width: 100%; min-width: 0; padding: 8px 12px; border: 0; background: var(--b2s-color-surface-soft, #f6f7f9); text-align: left; cursor: pointer; }
  .share__head code { min-width: 0; color: var(--b2s-color-text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-family: var(--b2s-font-mono); font-size: var(--b2s-fs-xs); }
  .share__sum { display: flex; align-items: center; gap: 8px; margin-left: auto; flex: none; }
  .share__sum small { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .car { width: 12px; flex: none; color: var(--b2s-color-text-muted); font-size: 10px; }
  .row { display: grid; grid-template-columns: minmax(0, 1fr) 80px 120px 130px; gap: 12px; align-items: center; padding: 7px 12px; border-top: 1px solid var(--b2s-color-border); color: inherit; text-decoration: none; font-size: var(--b2s-fs-sm); }
  a.row:hover { background: var(--b2s-color-surface-soft, #f6f7f9); }
  .row--head { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; }
  .name { display: flex; align-items: baseline; gap: 10px; min-width: 0; }
  .name strong { font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .name small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--b2s-color-text-muted); font-family: var(--b2s-font-mono); font-size: var(--b2s-font-micro); }
  .muted { color: var(--b2s-color-text-muted); }
  .ok { color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
  .calm { display: flex; justify-content: space-between; align-items: center; padding: 8px 12px; border-top: 1px solid var(--b2s-color-border); color: var(--b2s-color-text-muted); font-size: var(--b2s-fs-xs); }
</style>
