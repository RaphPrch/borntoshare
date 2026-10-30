<script lang="ts">
  import { t } from '$lib/i18n';
  import { goto } from '$app/navigation';
  import { formatDateTime, timeAgo } from '$lib/utils/format';
  import { endpointOperationalStateLabel, endpointOperationalStateVariant } from '$lib/mappers/entity-status.mapper';
  import type { StorageEndpointOverview } from '$lib/api/storage-endpoints';
  import type { StatusVariant } from '$lib/utils/status';

  type Filter = 'all' | 'success' | 'error' | 'other';

  /** Home of the file servers: fleet wall, searchable list and a summary; a server opens on its detail page. */
  export let endpoints: StorageEndpointOverview[] = [];
  export let onAdd: () => void = () => {};

  const PAGE_SIZE = 12;
  const TONE: Record<StatusVariant, string> = { success: 'ok', warning: 'warn', info: 'read', error: 'bad', disabled: '', muted: '' };

  let query = '';
  let filter: Filter = 'all';
  let listPage = 0;
  let selectedId: number | null = null;

  const variantOf = (ep: StorageEndpointOverview): StatusVariant => endpointOperationalStateVariant(ep.operational_state);
  const label = (ep: StorageEndpointOverview): string => endpointOperationalStateLabel(ep.operational_state);
  const filterOf = (ep: StorageEndpointOverview): Filter => {
    const variant = variantOf(ep);
    return variant === 'success' || variant === 'error' ? variant : 'other';
  };
  const address = (ep: StorageEndpointOverview): string => String(ep.host ?? '').trim();
  const folders = (ep: StorageEndpointOverview): number => Number(ep.roots_count ?? 0);
  const lastTest = (ep: StorageEndpointOverview): string => (ep.last_probe_at ? timeAgo(ep.last_probe_at) : t('Never'));
  const open = (ep: StorageEndpointOverview): void => void goto(`/admin/storage-endpoints/${ep.id}`);

  // What is wrong comes first: the eye goes to the top left of the wall
  const RANK: Record<Filter, number> = { error: 0, other: 1, success: 2, all: 3 };
  $: sorted = [...endpoints].sort(
    (a, b) => RANK[filterOf(a)] - RANK[filterOf(b)] || String(a.name ?? '').localeCompare(String(b.name ?? ''), 'fr', { numeric: true })
  );
  $: needle = query.trim().toLowerCase();
  $: visible = sorted.filter(
    (ep) =>
      (filter === 'all' || filterOf(ep) === filter) &&
      (!needle || `${ep.name ?? ''} ${address(ep)} ${ep.zone_name ?? ''}`.toLowerCase().includes(needle))
  );
  $: filter, needle, (listPage = 0);
  $: pageCount = Math.max(1, Math.ceil(visible.length / PAGE_SIZE));
  $: pageRows = visible.slice(listPage * PAGE_SIZE, listPage * PAGE_SIZE + PAGE_SIZE);
  $: selected = endpoints.find((ep) => ep.id === selectedId) ?? null;
  $: reachable = endpoints.filter((ep) => filterOf(ep) === 'success').length;
  $: down = endpoints.filter((ep) => filterOf(ep) === 'error').length;
  $: filters = [
    { key: 'all' as Filter, label: t('All'), count: endpoints.length },
    { key: 'error' as Filter, label: t('Unreachable'), count: down },
    { key: 'other' as Filter, label: t('To check'), count: endpoints.length - reachable - down },
    { key: 'success' as Filter, label: t('Reachable'), count: reachable }
  ];

  function pick(ep: StorageEndpointOverview): void {
    selectedId = ep.id;
    // The wall can select a server of another page of the list
    const index = visible.findIndex((row) => row.id === ep.id);
    if (index >= 0) listPage = Math.floor(index / PAGE_SIZE);
  }
</script>

<div class="sv">
  <header class="sv__head">
    <div class="sv__title">
      <h1>{t('File servers')}</h1>
      <p>
        {t('{servers} servers · {reachable} reachable · {folders} folders', {
          servers: endpoints.length,
          reachable,
          folders: endpoints.reduce((total, ep) => total + folders(ep), 0)
        })}
      </p>
    </div>
    <label class="sv__search">
      <i class="bi bi-search" aria-hidden="true"></i>
      <input type="search" aria-label={t('Search file servers')} placeholder={t('Search name, host, zone…')} bind:value={query} />
    </label>
    <button type="button" class="b2s-btn b2s-btn-primary" on:click={onAdd}>
      <i class="bi bi-plus-lg" aria-hidden="true"></i>{t('Add a server')}
    </button>
  </header>

  <section class="sv__panel sv__wall" aria-label={t('Fleet status')}>
    <div class="sv__wall-head">
      <strong>{t('Fleet status')}</strong>
      <span>
        <span><i class="dot ok"></i>{t('Reachable')}</span>
        <span><i class="dot other"></i>{t('To check')}</span>
        <span><i class="dot bad"></i>{t('Unreachable')}</span>
      </span>
    </div>
    <div class="sv__cells">
      {#each sorted as ep (ep.id)}
        <button
          type="button"
          class={`sv__cell ${TONE[variantOf(ep)] || 'other'}`}
          class:sel={ep.id === selectedId}
          title={`${ep.name} · ${label(ep)}`}
          aria-label={`${ep.name} · ${label(ep)}`}
          on:click={() => pick(ep)}
          on:dblclick={() => open(ep)}
        ></button>
      {/each}
    </div>
  </section>

  <div class="sv__chips" role="group" aria-label={t('Filters')}>
    {#each filters as item (item.key)}
      <button type="button" class:on={filter === item.key} aria-pressed={filter === item.key} on:click={() => (filter = item.key)}>{item.label} · {item.count}</button>
    {/each}
  </div>

  <div class="sv__body">
    <section class="sv__panel sv__list">
      <table>
        <thead>
          <tr><th>{t('Server')}</th><th class="w-zone">{t('Zone')}</th><th class="w-num">{t('Folders')}</th><th class="w-state">{t('State')}</th><th class="w-last">{t('Last test')}</th></tr>
        </thead>
        <tbody>
          {#each pageRows as ep (ep.id)}
            <tr class:sel={ep.id === selectedId} on:click={() => pick(ep)} on:dblclick={() => open(ep)}>
              <td>
                <button type="button" class="sv__name">{ep.name}{#if address(ep)}<code>{address(ep)}</code>{/if}</button>
              </td>
              <td>{ep.zone_name ?? '—'}</td>
              <td>{folders(ep)}</td>
              <td><span class={`tag ${TONE[variantOf(ep)]}`}>{label(ep)}</span></td>
              <td class="muted" title={ep.last_probe_at ? formatDateTime(ep.last_probe_at) : undefined}>{lastTest(ep)}</td>
            </tr>
          {:else}
            <tr><td colspan="5" class="sv__empty">{t('No server matches your search.')}</td></tr>
          {/each}
        </tbody>
      </table>
      <div class="sv__pager">
        <span>
          {#if visible.length}
            {t('{from}–{to} of {total}', { from: listPage * PAGE_SIZE + 1, to: Math.min(visible.length, listPage * PAGE_SIZE + PAGE_SIZE), total: visible.length })}
          {/if}
        </span>
        <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" disabled={listPage === 0} on:click={() => (listPage -= 1)}>{t('Previous')}</button>
        <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" disabled={listPage >= pageCount - 1} on:click={() => (listPage += 1)}>{t('Next')}</button>
      </div>
    </section>

    <aside class="sv__panel sv__side" aria-label={t('Details')}>
      {#if selected}
        <div>
          <span class={`tag ${TONE[variantOf(selected)]}`}>{label(selected)}</span>
          <h2>{selected.name}</h2>
          <code>{address(selected) || '—'}{selected.port ? `:${selected.port}` : ''} · {selected.zone_name ?? '—'}</code>
        </div>
        {#if String(selected.last_probe_message ?? '').includes(' ')}<p>{selected.last_probe_message}</p>{/if}
        <dl>
          <div><dt>{t('Folders')}</dt><dd>{folders(selected)}</dd></div>
          <div><dt>{t('Last test')}</dt><dd>{selected.last_probe_at ? timeAgo(selected.last_probe_at) : t('Not tested yet')}</dd></div>
          <div><dt>{t('Requests')}</dt><dd>{Number(selected.pending_requests_count ?? 0)}</dd></div>
          <div><dt>{t('Account')}</dt><dd><code>{selected.auth_username || selected.bind_dn || '—'}</code></dd></div>
        </dl>
        <button type="button" class="b2s-btn b2s-btn-primary" on:click={() => selected && open(selected)}>{t('Open the server')}</button>
      {:else}
        <div class="sv__side-empty">
          <i class="bi bi-hdd-network" aria-hidden="true"></i>
          <p>{t('Select a server on the wall or in the list.')}</p>
        </div>
      {/if}
    </aside>
  </div>
</div>

<style>
  .sv { display: flex; flex-direction: column; gap: 18px; padding: var(--b2s-page-padding); }
  .sv__head { display: flex; align-items: flex-end; gap: 12px; }
  .sv__title { flex: 1 1 320px; min-width: 0; }
  .sv__title h1 { margin: 0; font-size: 38px; line-height: 1.05; font-weight: 600; letter-spacing: -.03em; }
  .sv__title p { margin: 6px 0 0; color: var(--b2s-color-text-muted); font-size: 15px; }
  .sv__search { flex: 0 1 340px; display: flex; align-items: center; gap: 10px; min-height: 44px; margin: 0; padding: 0 14px; border-radius: 12px; background: var(--b2s-color-surface); border: 1px solid var(--b2s-color-border-strong); color: var(--b2s-color-text-muted); }
  .sv__search:focus-within { border-color: var(--b2s-color-text); }
  .sv__search input { flex: 1; min-width: 0; border: 0; outline: 0; background: transparent; color: var(--b2s-color-text); font: inherit; }
  .sv__panel { background: var(--b2s-color-surface); border: 1px solid var(--b2s-color-border); border-radius: 18px; box-shadow: 0 1px 2px rgba(14, 18, 24, .05), 0 8px 24px rgba(14, 18, 24, .06); }
  .sv__wall { padding: 16px; }
  .sv__wall-head { display: flex; justify-content: space-between; gap: 8px; margin-bottom: 12px; }
  .sv__wall-head strong { font-weight: 600; }
  .sv__wall-head > span { display: flex; gap: 14px; font-size: 12px; color: var(--b2s-color-text-muted); }
  .dot { display: inline-block; width: 8px; height: 8px; margin-right: 5px; border-radius: 50%; }
  .dot.ok, .sv__cell.ok { background: var(--b2s-color-success); }
  .dot.other, .sv__cell.other, .sv__cell.read, .sv__cell.warn { background: var(--b2s-color-warning); }
  .dot.bad, .sv__cell.bad { background: var(--b2s-color-danger); }
  .sv__cells { display: flex; flex-wrap: wrap; gap: 6px; }
  .sv__cell { width: 30px; height: 30px; padding: 0; border: 0; border-radius: 7px; cursor: pointer; transition: transform .1s; }
  .sv__cell:hover { transform: scale(1.2); }
  .sv__cell.sel { outline: 2px solid var(--b2s-color-text); outline-offset: 2px; }
  .sv__chips { display: flex; flex-wrap: wrap; gap: 8px; }
  .sv__chips button { min-height: 36px; padding: 0 13px; border-radius: 999px; border: 1px solid var(--b2s-color-border-strong); background: var(--b2s-color-surface); color: var(--b2s-color-text-muted); font: inherit; font-size: 13px; cursor: pointer; }
  .sv__chips button.on { background: var(--b2s-color-text); border-color: var(--b2s-color-text); color: #fff; font-weight: 600; }
  .sv__body { display: flex; align-items: flex-start; gap: 18px; }
  .sv__list { flex: 1; min-width: 0; overflow: hidden; }
  .sv__list table { width: 100%; border-collapse: collapse; }
  .sv__list th { text-align: left; font-size: 12px; font-weight: 500; color: var(--b2s-color-text-muted); padding: 10px 14px; border-bottom: 1px solid var(--b2s-color-border); }
  .sv__list td { padding: 10px 14px; border-bottom: 1px solid var(--b2s-color-border); vertical-align: middle; }
  .sv__list tbody tr { cursor: pointer; }
  .sv__list tbody tr:hover td { background: var(--b2s-color-surface-soft); }
  .sv__list tbody tr.sel td { background: var(--b2s-accent-soft); }
  .w-zone { width: 150px; }
  .w-num { width: 90px; }
  .w-state { width: 130px; }
  .w-last { width: 120px; }
  .muted { font-size: 12px; color: var(--b2s-color-text-muted); }
  .sv__name { padding: 0; border: 0; background: none; color: inherit; font: inherit; font-weight: 500; text-align: left; cursor: pointer; }
  .sv__name code { display: block; font-family: var(--b2s-font-mono); font-size: 12px; font-weight: 400; color: var(--b2s-color-text-muted); }
  .sv__pager { display: flex; align-items: center; gap: 6px; padding: 12px 14px; font-size: 12px; color: var(--b2s-color-text-muted); }
  .sv__pager span { margin-right: auto; }
  .sv__empty { padding: 24px; text-align: center; color: var(--b2s-color-text-muted); }
  .sv__side { flex: 0 0 380px; position: sticky; top: 16px; padding: 20px; display: flex; flex-direction: column; gap: 16px; }
  .sv__side h2 { margin: 10px 0 4px; font-size: 25px; font-weight: 600; letter-spacing: -.02em; overflow-wrap: anywhere; }
  .sv__side code { font-family: var(--b2s-font-mono); font-size: 12px; color: var(--b2s-color-text-muted); overflow-wrap: anywhere; }
  .sv__side p { margin: 0; font-size: 14px; overflow-wrap: anywhere; }
  .sv__side dl { margin: 0; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px 10px; }
  .sv__side dt { font-size: 12px; font-weight: 400; color: var(--b2s-color-text-muted); }
  .sv__side dd { margin: 0; font-weight: 500; }
  .sv__side-empty { display: grid; justify-items: center; gap: 10px; padding: 40px 24px; text-align: center; color: var(--b2s-color-text-muted); }
  .sv__side-empty i { font-size: 26px; }
  .sv__side-empty p { margin: 0; }
  .tag { display: inline-flex; align-items: center; font-size: 12px; font-weight: 500; padding: 3px 9px; border-radius: 999px; background: var(--b2s-color-neutral-soft); color: var(--b2s-color-text); white-space: nowrap; }
  .tag.ok { background: var(--b2s-color-success-soft); color: var(--b2s-color-success); }
  .tag.warn { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning); }
  .tag.bad { background: var(--b2s-color-danger-soft); color: var(--b2s-color-danger); }
  .tag.read { background: var(--b2s-color-info-soft); color: var(--b2s-color-info); }
</style>
