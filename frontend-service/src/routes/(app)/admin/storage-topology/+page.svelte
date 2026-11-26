<script lang="ts">
  /**
   * Storage Topology (Administration › Storage Endpoints › Topology): zone → server → volume → share → governed folder,
   * and the DFS namespaces of each zone. Explored one level at a time (the address keeps where one is): the overview
   * counts, a server lists its shares, the folders of a share come page by page. States from core-service
   * (/storage-topology): available, unavailable, degraded, unknown; « stale » beside them.
   */
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
  import { apiGetData } from '$lib/api/client';
  import { t } from '$lib/i18n';
  import { formatBytes } from '$lib/utils/format';
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import EmptyStateInline from '$lib/components/ui/EmptyStateInline.svelte';
  import StatusBadge from '$lib/components/ui/StatusBadge.svelte';
  import RelativeTime from '$lib/components/ui/RelativeTime.svelte';
  import SegmentedFilter from '$lib/components/ui/SegmentedFilter.svelte';
  import SearchField from '$lib/components/ui/SearchField.svelte';
  import Drawer from '$lib/components/ui/Drawer.svelte';
  import { DFS_LINK_LABEL, STATE_META, capacityLine, topologyLevel, topologyHref, type TopologyPlace } from '$lib/utils/storage-topology';

  const PAGE = 50;
  let overview = $state<any>(null);
  let server = $state<any>(null);
  let dfs = $state<any>(null);
  let roots = $state<any>(null);
  let error = $state('');
  let loading = $state(false);
  let rootsLoading = $state(false);
  let rootState = $state('all');
  let rootQuery = $state('');
  // The filter typed, applied on Enter (each key does not reload)
  let applied = $state('');
  let offset = $state(0);
  let selected = $state<any>(null);

  let place = $derived<TopologyPlace>(topologyLevel($page.url.searchParams));
  let zone = $derived(place.zone ? overview?.zones?.find((z: any) => z.id === place.zone) ?? null : null);

  const go = (next: TopologyPlace) => {
    offset = 0;
    rootState = 'all';
    rootQuery = '';
    applied = '';
    void goto(topologyHref(next), { keepFocus: true, noScroll: true });
  };
  const fail = (failure: unknown) => (error = failure instanceof Error ? failure.message : t('Unable to load the storage topology.'));

  // The overview once (it is small: counts only); a server, a DFS namespace, the folders of a share when opened
  $effect(() => {
    if (overview) return;
    apiGetData(fetch, '/storage-topology').then((data) => (overview = data)).catch(fail);
  });
  $effect(() => {
    const id = place.server;
    server = null;
    if (!id) return;
    loading = true;
    apiGetData(fetch, `/storage-topology/servers/${id}`).then((data) => (server = data)).catch(fail).finally(() => (loading = false));
  });
  $effect(() => {
    const id = place.dfs;
    dfs = null;
    void offset;
    if (!id) return;
    loading = true;
    apiGetData(fetch, `/storage-topology/dfs/${id}`, { offset, limit: PAGE, ...(applied ? { q: applied } : {}) })
      .then((data) => (dfs = data)).catch(fail).finally(() => (loading = false));
  });
  $effect(() => {
    const { server: id, share, volume } = place;
    void offset; void rootState; void applied;
    roots = null;
    if (!id || !share) return;
    rootsLoading = true;
    apiGetData(fetch, `/storage-topology/servers/${id}/roots`, {
      offset, limit: PAGE, ...(share ? { share } : {}), ...(volume ? { volume } : {}),
      ...(rootState !== 'all' ? { state: rootState } : {}), ...(applied ? { q: applied } : {})
    }).then((data) => (roots = data)).catch(fail).finally(() => (rootsLoading = false));
  });

  let shareNode = $derived(place.share ? server?.shares?.find((s: any) => s.key === place.share) ?? null : null);
  let shares = $derived((server?.shares ?? []).filter((s: any) => !place.volume || s.volume === place.volume));
  let pager = $derived(place.dfs ? dfs?.links : roots);
  // Where one is, from the zones down
  let crumbs = $derived([
    { label: t('All zones'), place: {} as TopologyPlace },
    ...(zone ? [{ label: zone.name, place: { zone: zone.id } }] : []),
    ...(server ? [{ label: server.server.name, place: { zone: place.zone, server: place.server } }] : []),
    ...(dfs ? [{ label: dfs.dfs.name, place: { zone: place.zone, dfs: place.dfs } }] : []),
    ...(place.volume ? [{ label: place.volume, place: { zone: place.zone, server: place.server, volume: place.volume } }] : []),
    ...(shareNode ? [{ label: shareNode.name, place }] : [])
  ]);
</script>

{#snippet state(node: any)}
  {#if node}
    <StatusBadge variant={STATE_META[node.state]?.variant ?? 'muted'} label={t(STATE_META[node.state]?.label ?? 'Unknown')} compact />
    {#if node.stale}<span class="v2-tag is-warn" title={t('The last collection is older than two synchronisation cycles.')}>{t('Stale collection')}</span>{/if}
  {/if}
{/snippet}

{#snippet facts(node: any)}
  <span class="st__facts">
    {#if node.collected_at}<span>{t('Collected')} <RelativeTime value={node.collected_at} /></span>{:else}<span>{t('Never collected')}</span>{/if}
    {#if node.capacity && capacityLine(node.capacity)}<span>{capacityLine(node.capacity, formatBytes, t)}</span>{/if}
    {#if node.alerts?.open}<span class={node.alerts.serious ? 'st__bad' : ''}><i class="bi bi-bell" aria-hidden="true"></i> {node.alerts.open}{#if node.alerts.serious} ({t('{n} serious', { n: node.alerts.serious })}){/if}</span>{/if}
  </span>
{/snippet}

<svelte:head><title>Storage Topology · BornToShare</title></svelte:head>

<section class="v2 st">
  <div class="v2-head">
    <div>
      <h1>Storage Topology</h1>
      <p>{t('Zones, servers, volumes, shares, DFS namespaces and governed folders, with the state of their last collection.')}</p>
    </div>
  </div>

  {#if error}<InlineAlert tone="error">{error}</InlineAlert>{/if}

  {#if !overview}
    {#if !error}<LoadingState block skeleton="rows">{t('Loading…')}</LoadingState>{/if}
  {:else}
    <nav class="st__crumbs" aria-label={t('Position in the topology')}>
      {#each crumbs as crumb, i (i)}
        {#if i < crumbs.length - 1}<button type="button" class="b2s-link-btn" onclick={() => go(crumb.place)}>{crumb.label}</button><i class="bi bi-chevron-right" aria-hidden="true"></i>
        {:else}<b>{crumb.label}</b>{/if}
      {/each}
    </nav>

    {#if !place.zone}
      <!-- Global view: one card per zone -->
      <div class="v2-stats">
        <div class="v2-stat"><b>{overview.summary.zones}</b><span>{t('Zones')}</span></div>
        <div class="v2-stat"><b>{overview.summary.servers}</b><span>{t('Servers')}</span></div>
        <div class="v2-stat"><b>{overview.summary.dfs}</b><span>{t('DFS namespaces')}</span></div>
        <div class="v2-stat"><b>{overview.summary.roots}</b><span>{t('Governed folders')}</span></div>
        <div class="v2-stat"><i class={`bi bi-hdd-network ${overview.summary.states.unavailable ? 'is-bad' : ''}`} aria-hidden="true"></i><b>{overview.summary.states.unavailable}</b><span>{t('Unavailable endpoints')}</span></div>
      </div>
      <p class="v2-hint">{t('A collection is stale after {h} h (two cycles of the data synchronisation). Unknown means nothing was collected yet: it is not an outage.', { h: Math.round(overview.freshness.stale_after_minutes / 60) })}</p>
      {#if overview.zones.length}
        <div class="st__grid">
          {#each overview.zones as z (z.id)}
            <button type="button" class="v2-sec st__card" onclick={() => go({ zone: z.id })}>
              <div class="st__card-h"><i class="bi bi-geo-alt" aria-hidden="true"></i><b>{z.name}</b>{@render state(z)}</div>
              <span class="st__counts">{t('{s} server(s) · {d} DFS · {r} folder(s)', { s: z.children.servers, d: z.children.dfs, r: z.children.roots })}</span>
              {@render facts(z)}
            </button>
          {/each}
        </div>
      {:else}
        <EmptyStateInline message={t('No zone yet.')} href="/admin/zones/new" actionLabel={t('Add a zone')} />
      {/if}

    {:else if zone && !place.server && !place.dfs}
      <!-- A zone: its servers and DFS namespaces -->
      <div class="v2-sec">
        <div class="v2-sh"><h2><i class="bi bi-geo-alt" aria-hidden="true"></i> {zone.name}</h2>{@render state(zone)}
          <div class="v2-sh__r"><a href={`/admin/zones/${zone.id}`}>{t('Open the zone')}</a></div></div>
        {@render facts(zone)}
      </div>
      <div class="v2-sec">
        <div class="v2-sh"><h2>{t('Servers')}</h2><span class="v2-tag is-mut">{zone.servers.length}</span></div>
        {#if zone.servers.length}
          <table class="b2s-table st__table">
            <thead><tr><th>{t('Server')}</th><th>{t('State')}</th><th>{t('Shares')}</th><th>{t('Volumes')}</th><th>{t('Folders')}</th><th>{t('Capacity')}</th><th>{t('Alerts')}</th><th>{t('Last collection')}</th></tr></thead>
            <tbody>
              {#each zone.servers as s (s.id)}
                <tr class="st__row" onclick={() => go({ zone: zone.id, server: s.id })}>
                  <td><b>{s.name}</b><small>{s.host ?? ''}</small></td>
                  <td>{@render state(s)}{#if s.message}<small class="st__bad">{s.message}</small>{/if}</td>
                  <td>{s.children.shares}</td>
                  <td>{s.children.volumes || '—'}</td>
                  <td>{s.children.roots}{#if s.children.roots_unavailable} <small class="st__bad">{t('{n} unavailable', { n: s.children.roots_unavailable })}</small>{/if}</td>
                  <td>{capacityLine(s.capacity, formatBytes, t) || '—'}</td>
                  <td>{s.alerts.open || '—'}</td>
                  <td>{#if s.collected_at}<RelativeTime value={s.collected_at} />{:else}{t('Never')}{/if}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        {:else}<EmptyStateInline message={t('No file server in this zone.')} />{/if}
      </div>
      {#if zone.dfs.length}
        <div class="v2-sec">
          <div class="v2-sh"><h2>{t('DFS namespaces')}</h2><span class="v2-tag is-mut">{zone.dfs.length}</span></div>
          <table class="b2s-table st__table">
            <thead><tr><th>{t('Namespace')}</th><th>{t('State')}</th><th>{t('DFS folders')}</th><th>{t('Last reading')}</th></tr></thead>
            <tbody>
              {#each zone.dfs as d (d.id)}
                <tr class="st__row" onclick={() => go({ zone: zone.id, dfs: d.id })}>
                  <td><b>{d.name}</b><small>{d.path ?? ''}</small></td>
                  <td>{@render state(d)}</td>
                  <td>{d.children.links}</td>
                  <td>{#if d.collected_at}<RelativeTime value={d.collected_at} />{:else}{t('Never')}{/if}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {/if}

    {:else if place.server}
      <!-- A server: volumes (when known), shares, then the folders of a share or a volume -->
      {#if loading && !server}<LoadingState block skeleton="rows">{t('Loading…')}</LoadingState>
      {:else if server}
        <div class="v2-sec">
          <div class="v2-sh"><h2><i class="bi bi-hdd-network" aria-hidden="true"></i> {server.server.name}</h2>{@render state(server.server)}
            <div class="v2-sh__r"><a href={`/admin/storage-endpoints/${server.server.id}`}>{t('Open the server')}</a></div></div>
          <p class="v2-hint">{server.server.host ?? ''} · {server.server.zone_name}{#if server.server.message} · <span class="st__bad">{server.server.message}</span>{/if}</p>
          {@render facts(server.server)}
          {#if server.volumes.length}
            <div class="st__volumes">
              {#each server.volumes as v (v.key)}
                <button type="button" class={`st__chip ${place.volume === v.name ? 'is-on' : ''}`} onclick={() => go({ zone: place.zone, server: place.server, ...(place.volume === v.name ? {} : { volume: v.name }) })}>
                  <i class="bi bi-device-hdd" aria-hidden="true"></i><b>{v.name}</b>{@render state(v)}
                  <small>{t('{s} share(s) · {r} folder(s)', { s: v.children.shares, r: v.children.roots })}{#if capacityLine(v.capacity)} · {capacityLine(v.capacity, formatBytes, t)}{/if}</small>
                </button>
              {/each}
            </div>
          {/if}
          <p class="v2-hint">{server.volumes.length
            ? t('Volumes come from the FSRM quota readings: {n} share(s) without a quota have no known volume and are listed under the server.', { n: server.shares_without_volume })
            : t('No volume known: they come from the FSRM quota readings, and none was read on this server.')}</p>
        </div>

        {#if !place.share}
          <div class="v2-sec">
            <div class="v2-sh"><h2>{place.volume ? t('Shares of {v}', { v: place.volume }) : t('Shares')}</h2><span class="v2-tag is-mut">{shares.length}</span></div>
            {#if shares.length}
              <table class="b2s-table st__table">
                <thead><tr><th>{t('Share')}</th><th>{t('State')}</th><th>{t('Volume')}</th><th>{t('Folders')}</th><th>{t('Capacity')}</th><th>{t('Alerts')}</th><th>{t('Oldest collection')}</th></tr></thead>
                <tbody>
                  {#each shares as s (s.key)}
                    <tr class="st__row" onclick={() => go({ zone: place.zone, server: place.server, volume: place.volume, share: s.key })}>
                      <td><b class="st__mono">{s.name}</b></td>
                      <td>{@render state(s)}</td>
                      <td>{s.volume ?? '—'}</td>
                      <td>{s.children.roots}{#if s.children.roots_unavailable} <small class="st__bad">{t('{n} unavailable', { n: s.children.roots_unavailable })}</small>{/if}</td>
                      <td>{capacityLine(s.capacity, formatBytes, t) || '—'}</td>
                      <td>{s.alerts.open || '—'}</td>
                      <td>{#if s.collected_at}<RelativeTime value={s.collected_at} />{:else}{t('Never')}{/if}</td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            {:else}<EmptyStateInline message={t('No governed folder on this server yet.')} />{/if}
          </div>
        {/if}

        {#if place.share}
            <div class="v2-sec">
              <div class="v2-sh"><h2>{t('Governed folders')}</h2>{#if roots}<span class="v2-tag is-mut">{roots.total}</span>{/if}
                <div class="v2-sh__r st__filters">
                  <SegmentedFilter options={[{ key: 'all', label: t('All') }, { key: 'available', label: t('Available') }, { key: 'unavailable', label: t('Unavailable') }, { key: 'unknown', label: t('Unknown') }, { key: 'stale', label: t('Stale') }]}
                    bind:value={rootState} onChange={() => (offset = 0)} />
                  <SearchField bind:value={rootQuery} placeholder={t('Filter')} ariaLabel={t('Filter')} onEnter={() => { offset = 0; applied = rootQuery.trim(); }} />
                </div></div>
              {#if rootsLoading && !roots}<LoadingState block skeleton="rows">{t('Loading…')}</LoadingState>
              {:else if roots?.items.length}
                <table class="b2s-table st__table">
                  <thead><tr><th>{t('Folder')}</th><th>{t('State')}</th><th>{t('Volume')}</th><th>{t('Capacity')}</th><th>{t('Alerts')}</th><th>{t('Last collection')}</th></tr></thead>
                  <tbody>
                    {#each roots.items as r (r.id)}
                      <tr class="st__row" onclick={() => (selected = r)}>
                        <td><b>{r.name}</b><small class="st__mono">{r.path}</small></td>
                        <td>{@render state(r)}</td>
                        <td>{r.volume ?? '—'}</td>
                        <td>{capacityLine(r.capacity, formatBytes, t) || '—'}</td>
                        <td>{r.alerts.open || '—'}</td>
                        <td>{#if r.collected_at}<RelativeTime value={r.collected_at} />{:else}{t('Never')}{/if}</td>
                      </tr>
                    {/each}
                  </tbody>
                </table>
              {:else if roots}<EmptyStateInline message={t('No folder matches.')} />{/if}
            </div>
        {/if}
      {/if}

    {:else if place.dfs}
      <!-- A DFS namespace: its folders and where they lead -->
      {#if loading && !dfs}<LoadingState block skeleton="rows">{t('Loading…')}</LoadingState>
      {:else if dfs}
        <div class="v2-sec">
          <div class="v2-sh"><h2><i class="bi bi-diagram-3" aria-hidden="true"></i> {dfs.dfs.name}</h2>{@render state(dfs.dfs)}
            <div class="v2-sh__r"><a href={`/admin/storage-endpoints/${dfs.dfs.id}`}>{t('Open the namespace')}</a></div></div>
          <p class="v2-hint st__mono">{dfs.dfs.path ?? ''}{#if dfs.dfs.error} · <span class="st__bad">{dfs.dfs.error}</span>{/if}</p>
          {@render facts(dfs.dfs)}
        </div>
        <div class="v2-sec">
          <div class="v2-sh"><h2>{t('DFS folders')}</h2><span class="v2-tag is-mut">{dfs.links.total}</span>
            <div class="v2-sh__r"><SearchField bind:value={rootQuery} placeholder={t('Filter')} ariaLabel={t('Filter')} onEnter={() => { offset = 0; applied = rootQuery.trim(); }} /></div></div>
          {#if dfs.links.items.length}
            <table class="b2s-table st__table">
              <thead><tr><th>{t('DFS folder')}</th><th>{t('Governance')}</th><th>{t('Targets')}</th></tr></thead>
              <tbody>
                {#each dfs.links.items as link (link.dfs_path)}
                  <tr>
                    <td class="st__mono">{link.dfs_path}</td>
                    <td><span class={`v2-tag is-${link.state === 'managed' ? 'ok' : link.state === 'partial' || link.state === 'to_manage' ? 'warn' : 'mut'}`}>{t(DFS_LINK_LABEL[link.state] ?? link.state)}</span></td>
                    <td>
                      {#each link.targets as target (target.unc)}
                        <div class="st__target">
                          <StatusBadge variant={STATE_META[target.state]?.variant ?? 'muted'} label={t(STATE_META[target.state]?.label ?? 'Unknown')} compact />
                          {#if target.storage_root_id}<a href={`/storage-roots?selected=${target.storage_root_id}`} class="st__mono">{target.unc}</a>
                          {:else}<span class="st__mono">{target.unc}</span>{/if}
                          {#if target.storage_endpoint_id}<button type="button" class="b2s-link-btn" onclick={() => go({ zone: place.zone, server: target.storage_endpoint_id })}>{target.storage_endpoint_name}</button>
                          {:else}<small>{t('Server not declared')}</small>{/if}
                        </div>
                      {/each}
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
          {:else}<EmptyStateInline message={t('No DFS folder read in this namespace.')} />{/if}
        </div>
      {/if}
    {:else}
      <EmptyStateInline message={t('This zone does not exist any more.')} />
    {/if}

    {#if pager && pager.total > pager.limit}
      <div class="v2-pager">
        <span>{t('{from}–{to} of {total}', { from: pager.offset + 1, to: Math.min(pager.offset + pager.limit, pager.total), total: pager.total })}</span>
        <div class="v2-pager__r">
          <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" disabled={pager.offset === 0} onclick={() => (offset = Math.max(0, pager.offset - PAGE))}>{t('Previous')}</button>
          <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" disabled={pager.offset + pager.limit >= pager.total} onclick={() => (offset = pager.offset + PAGE)}>{t('Next')}</button>
        </div>
      </div>
    {/if}
  {/if}
</section>

<Drawer open={Boolean(selected)} title={selected?.name ?? ''} subtitle={selected?.path ?? ''} iconClass="bi-folder2" onClose={() => (selected = null)}>
  {#if selected}
    <dl class="st__dl">
      <dt>{t('State')}</dt><dd>{@render state(selected)}</dd>
      <dt>{t('Last collection')}</dt><dd>{#if selected.collected_at}<RelativeTime value={selected.collected_at} />{:else}{t('Never collected')}{/if}</dd>
      {#if selected.message}<dt>{t('Message')}</dt><dd class="st__bad">{selected.message}</dd>{/if}
      <dt>{t('Volume')}</dt><dd>{selected.volume ?? t('Not known')}</dd>
      <dt>{t('Quota')}</dt><dd>{selected.capacity.quota_limit_bytes != null ? `${formatBytes(selected.capacity.quota_used_bytes)} / ${formatBytes(selected.capacity.quota_limit_bytes)}` : t('None read')}</dd>
      <dt>{t('Measured size')}</dt><dd>{selected.capacity.measured_bytes != null ? formatBytes(selected.capacity.measured_bytes) : t('Not measured')}</dd>
      <dt>{t('Open alerts')}</dt><dd>{selected.alerts.open}{#if selected.alerts.serious} ({t('{n} serious', { n: selected.alerts.serious })}){/if}</dd>
    </dl>
    <a class="b2s-btn b2s-btn-primary" href={`/storage-roots?selected=${selected.id}`}><i class="bi bi-folder2-open" aria-hidden="true"></i>{t('Open its sheet')}</a>
  {/if}
</Drawer>

<style>
  .st__crumbs { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin: 0 0 12px; font-size: 13px; }
  .st__crumbs .bi { color: var(--b2s-color-text-muted); font-size: 11px; }
  .st__grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
  .st__card { display: flex; flex-direction: column; gap: 6px; text-align: left; cursor: pointer; border: 1px solid var(--b2s-color-border); }
  .st__card:hover, .st__card:focus-visible { border-color: var(--b2s-accent); }
  .st__card-h { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
  .st__counts { font-size: 13px; }
  .st__facts { display: flex; flex-wrap: wrap; gap: 4px 14px; font-size: 12px; color: var(--b2s-color-text-muted); }
  .st__bad { color: var(--b2s-color-danger); }
  .st__table td small { display: block; color: var(--b2s-color-text-muted); }
  .st__table td small.st__bad { color: var(--b2s-color-danger); }
  .st__row { cursor: pointer; }
  .st__mono { font-family: var(--b2s-font-mono, monospace); font-size: 12px; overflow-wrap: anywhere; }
  .st__volumes { display: flex; flex-wrap: wrap; gap: 8px; margin: 8px 0; }
  .st__chip { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; padding: 6px 10px; border: 1px solid var(--b2s-color-border);
    border-radius: var(--b2s-radius-md); background: var(--b2s-color-surface); text-align: left; }
  .st__chip.is-on { border-color: var(--b2s-accent); }
  .st__chip small { flex-basis: 100%; color: var(--b2s-color-text-muted); }
  .st__filters { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
  .st__target { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-bottom: 4px; }
  .st__dl { display: grid; grid-template-columns: max-content 1fr; gap: 8px 16px; margin: 0 0 16px; }
  .st__dl dt { color: var(--b2s-color-text-muted); }
  .st__dl dd { margin: 0; }
</style>
