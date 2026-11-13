<script lang="ts">
  import { goto, invalidateAll } from '$app/navigation';
  import { onMount } from 'svelte';
  import { t } from '$lib/i18n';
  import { toast } from '$lib/stores/toast';
  import { deleteStorageEndpoint } from '$lib/api/storage-endpoints';
  import { dfsCounts, dfsReadIsStale, loadDfsInfo, readDfsAgain, type DfsInfo } from '$lib/components/storage-endpoints/dfs-namespace';
  import EntityHeroCard from '$lib/components/entity/EntityHeroCard.svelte';
  import ConfirmActionModal from '$lib/components/ui/ConfirmActionModal.svelte';
  import CountUp from '$lib/components/ui/CountUp.svelte';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import RelativeTime from '$lib/components/ui/RelativeTime.svelte';

  
  interface Props {
    /**
   * A server that hosts DFS namespaces (DFS01): shown once, as a server. Its namespaces are listed here (each keeps
   * its own page, to manage its DFS folders); the server can be read again or removed from BornToShare as a whole.
   */
    server: string;
    zoneName?: string;
    namespaces?: Array<Record<string, any>>;
    endpointId: (ep: Record<string, any>) => number;
    endpointName: (ep: Record<string, any>) => string;
  }

  let {
    server,
    zoneName = '',
    namespaces = [],
    endpointId,
    endpointName
  }: Props = $props();

  type Row = { id: number; name: string; info: DfsInfo | null; error: string };
  let rows: Row[] = $state([]);
  let loading = $state(true);
  let reading = $state(false);
  let readDone = $state(0);
  let askDelete = $state(false);
  let deleting = $state(false);

  async function load() {
    loading = true;
    rows = await Promise.all(namespaces.map(async (ep): Promise<Row> => {
      try {
        return { id: endpointId(ep), name: endpointName(ep), info: await loadDfsInfo(fetch, endpointId(ep)), error: '' };
      } catch (error) {
        return { id: endpointId(ep), name: endpointName(ep), info: null, error: error instanceof Error ? error.message : t('Unable to read this namespace.') };
      }
    }));
    rows = rows.sort((a, b) => a.name.localeCompare(b.name, 'fr', { sensitivity: 'base' }));
    loading = false;
  }
  onMount(load);

  let totals = $derived(rows.reduce((sum, row) => {
    const counts = dfsCounts(row.info);
    return { links: sum.links + counts.all, managed: sum.managed + counts.managed, todo: sum.todo + counts.todo };
  }, { links: 0, managed: 0, todo: 0 }));
  let failed = $derived(rows.filter((row) => row.error || row.info?.error).length);
  let stale = $derived(rows.filter((row) => !row.error && !row.info?.error && dfsReadIsStale(row.info)).length);
  let account = $derived(String(namespaces[0]?.bind_dn ?? namespaces[0]?.auth_username ?? ''));

  async function readAll() {
    if (reading) return;
    reading = true;
    readDone = 0;
    let errors = 0;
    for (const row of rows) {
      const ep = namespaces.find((item) => endpointId(item) === row.id);
      try {
        if (ep && row.info?.path) await readDfsAgain(fetch, ep, row.info.path, row.info.type);
      } catch {
        errors += 1;
      }
      readDone += 1;
    }
    reading = false;
    await load();
    if (errors) toast.warning(t('{count} namespace(s) could not be read.', { count: errors }));
    else toast.success(t('{count} namespace(s) read again.', { count: rows.length }));
  }

  async function removeServer() {
    deleting = true;
    const refused: string[] = [];
    for (const ep of namespaces) {
      try {
        await deleteStorageEndpoint(fetch, endpointId(ep));
      } catch (error) {
        refused.push(`${endpointName(ep)} : ${error instanceof Error ? error.message : '—'}`);
      }
    }
    deleting = false;
    askDelete = false;
    if (refused.length) {
      toast.error(t('{count} namespace(s) not removed: {list}', { count: refused.length, list: refused.slice(0, 3).join(' · ') }));
      await invalidateAll();
      return;
    }
    toast.success(t('{server} removed from BornToShare.', { server }));
    await goto('/admin/storage-endpoints', { invalidateAll: true });
  }
</script>

<div class="dsv">
  <EntityHeroCard
    icon="bi-diagram-3"
    iconTone="blue"
    crumbs={[t('DFS servers'), zoneName]}
    title={server}
    statusLabel={failed ? t('Read failed') : stale ? t('To read again') : t('Up to date')}
    statusTone={failed ? 'danger' : stale ? 'warning' : 'success'}
    path={`\\\\${server}`}
    chips={[
      { label: t('Hosts {count} DFS namespace(s)', { count: namespaces.length }), icon: 'bi-diagram-3' },
      ...(account ? [{ label: account, icon: 'bi-person-badge', mono: true }] : [])
    ]}
    actions={[
      { key: 'read', label: reading ? t('Reading {done}/{total}…', { done: readDone, total: rows.length }) : t('Read every namespace again'),
        icon: reading ? 'bi-arrow-repeat sed-spin' : 'bi-arrow-clockwise', variant: 'primary', disabled: reading || loading, onClick: () => void readAll() },
      { key: 'delete', label: t('Remove {server} from BornToShare', { server }), icon: 'bi-trash', variant: 'danger', overflow: true, onClick: () => (askDelete = true) }
    ]}
    actionsAriaLabel={t('DFS server actions')}
  />

  <section class="b2s-stat-tiles" aria-label={t('DFS server summary')}>
    <div class="b2s-stat-tile"><span>{t('DFS namespaces')}</span><b><CountUp value={namespaces.length} /></b><small>{t('hosted on {server}', { server })}</small></div>
    <div class="b2s-stat-tile"><span>{t('DFS folders')}</span><b>{#if loading}—{:else}<CountUp value={totals.links} />{/if}</b><small>{t('in all its namespaces')}</small></div>
    <div class="b2s-stat-tile"><span>{t('Managed')}</span><b class:is-ok={!loading && totals.links > 0 && totals.managed === totals.links}>{#if loading}—{:else}<CountUp value={totals.managed} />{/if}</b><small>{t('their targets are governed folders')}</small></div>
    <div class="b2s-stat-tile"><span>{t('To manage')}</span><b class:is-warn={totals.todo > 0}>{#if loading}—{:else}<CountUp value={totals.todo} />{/if}</b><small>{t('open the namespace to manage them')}</small></div>
  </section>

  <section class="dsv__card" aria-label={t('DFS namespaces')}>
    <header><h2>{t('Namespaces hosted on {server}', { server })}</h2><a class="b2s-link-btn" href="/storage-roots">{t('See them in Folders')}</a></header>
    {#if loading}
      <LoadingState skeleton="rows" rows={6} />
    {:else}
      <div class="b2s-table-wrap">
        <table class="b2s-table">
          <thead><tr><th>{t('Namespace')}</th><th>{t('Path')}</th><th>{t('DFS folders')}</th><th>{t('Managed')}</th><th>{t('To manage')}</th><th>{t('Read')}</th><th></th></tr></thead>
          <tbody>
            {#each rows as row (row.id)}
              {@const counts = dfsCounts(row.info)}
              <tr>
                <td><strong>{row.name}</strong></td>
                <td><code data-copy={row.info?.path ?? ''}>{row.info?.path ?? '—'}</code></td>
                <td class="dsv__num">{row.info ? counts.all : '—'}</td>
                <td class="dsv__num">{row.info ? counts.managed : '—'}</td>
                <td class="dsv__num" class:is-warn={counts.todo > 0}>{row.info ? counts.todo || '—' : '—'}</td>
                <td>
                  {#if row.error || row.info?.error}<span class="dsv__bad" title={row.error || row.info?.error || ''}>{t('Read failed')}</span>
                  {:else if row.info?.read_at}<RelativeTime value={row.info.read_at} />
                  {:else}{t('Never read')}{/if}
                </td>
                <td class="dsv__open"><a class="b2s-btn b2s-btn-secondary b2s-btn-sm" href={`/admin/storage-endpoints/${row.id}`}>{t('Open')}</a></td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}
  </section>
</div>

<ConfirmActionModal
  open={askDelete}
  onClose={() => (askDelete = false)}
  onConfirm={removeServer}
  busy={deleting}
  title={t('Remove {server} from BornToShare?', { server })}
  subtitle={t('Nothing is changed on the server: its DFS namespaces stay as they are.')}
  confirmLabel={t('Remove {server}', { server })}
  confirmVariant="danger"
  severity="danger"
  impactItems={[
    t('Its {count} DFS namespace(s) are no longer read by BornToShare.', { count: namespaces.length }),
    t('The DFS paths (\\\\corp.local\\…) no longer show in Folders; the governed folders stay, on their file servers.'),
    t('It can be declared again later (Servers › New endpoint).')
  ]}
/>

<style>
  .dsv { display: grid; gap: 16px; min-width: 0; }
  .dsv__card { display: flex; flex-direction: column; gap: 10px; min-width: 0; padding: 16px 18px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); background: var(--b2s-color-surface); }
  .dsv__card header { display: flex; align-items: center; gap: 12px; }
  .dsv__card h2 { margin: 0 auto 0 0; font-size: var(--b2s-fs-md); font-weight: 600; }
  .dsv__num { font-variant-numeric: tabular-nums; }
  .dsv__num.is-warn { color: var(--b2s-color-warning-strong); font-weight: 600; }
  .dsv__bad { color: var(--b2s-color-danger-strong); font-weight: 600; }
  .dsv__open { text-align: right; }
  code { font-family: var(--b2s-font-mono); font-size: var(--b2s-fs-xs); color: var(--b2s-color-text-muted); background: none; }
</style>
