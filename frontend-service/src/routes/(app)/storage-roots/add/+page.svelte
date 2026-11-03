<script lang="ts">
  import SegmentedFilter from '$lib/components/ui/SegmentedFilter.svelte';
  import { onDestroy, onMount } from 'svelte';
  import { beforeNavigate, invalidate } from '$app/navigation';
  import { t } from '$lib/i18n';
  import { apiGetData, apiPostData } from '$lib/api/client';
  import GovernancePicker from '$lib/components/storage-roots/GovernancePicker.svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import {
    buildStorageEndpointProbeRequestFromEndpoint,
    parseStorageEndpointProbeRoots,
    resolveStorageEndpointProbeConfig,
    validateStorageEndpointProbeConfig
  } from '$lib/jobs/storage-endpoint-probe';
  import { runProbeWithPolling, syncStorageRootDiscoveryForEndpoint } from '$lib/jobs/probe-runner';
  import { endpointIdOf, endpointNameOf, endpointZoneIdOf } from '$lib/mappers/storage-roots.mapper';
  import { humanizeFileServerMessage } from '$lib/errors/file-server';
  import { formatDateTime } from '$lib/utils/format';

  type Option = { id: number; label: string; hint?: string };
  export let data: {
    endpoints: Record<string, any>[];
    catalog: Record<string, any>[];
    tags: Option[];
    people: Option[];
    minGuardians: number;
  };

  type Folder = { storage_endpoint_id: number; storage_endpoint_name: string; name: string; root_path: string; managed: boolean };
  type Server = {
    id: number;
    name: string;
    zoneId: number;
    zone: string;
    state: 'ok' | 'bad' | 'none';
    newCount: number;
    total: number;
    discoveredAt: string | null;
    raw: Record<string, any>;
  };
  type Failure = { name: string; root_path: string; message: string };

  const BATCH_SIZE = 25;
  const SEARCH_DELAY_MS = 250;

  const keyOf = (folder: Pick<Folder, 'storage_endpoint_id' | 'root_path'>) => `${folder.storage_endpoint_id}|${folder.root_path}`;

  let foldersByServer: Record<number, Folder[]> = {};
  let loadError = '';
  let loadingFolders = false;
  let currentId: number | null = null;
  let scanning: Record<number, boolean> = {};
  let scanErrors: Record<number, string> = {};

  let selected = new Map<string, Folder>();
  let anchor: number | null = null;

  let serverQuery = '';
  let serverFilter: 'all' | 'selected' | 'bad' = 'all';
  let openZones: Record<string, boolean> = {};
  let folderQuery = '';
  let folderFilter: 'new' | 'managed' | 'all' = 'new';

  let globalQuery = '';
  let globalItems: Folder[] = [];
  let globalTotal = 0;
  let searching = false;
  let searchTimer: ReturnType<typeof setTimeout> | undefined;
  let searchTicket = 0;

  let guardianIds: number[] = [];
  let tagIds: number[] = [];
  let groupPreview: { read: string; write: string } | null = null;
  let previewKey = '';

  let running = false;
  let done = 0;
  let total = 0;
  let createdIds: number[] = [];
  let warnings: string[] = [];
  let failures: Failure[] = [];
  let finished = false;

  $: catalogById = new Map(data.catalog.map((row) => [Number(row.storage_endpoint_id), row]));
  // A disabled server cannot receive new folders
  $: servers = data.endpoints
    .filter((raw) => raw?.is_active !== false && raw?.is_active !== 0 && String(raw?.status ?? '').toLowerCase() !== 'disabled')
    .map((raw): Server => {
      const id = endpointIdOf(raw);
      const entry = catalogById.get(id);
      const probe = String(raw?.last_probe_status ?? raw?.probe_status ?? '').toLowerCase();
      const discoveredAt = entry?.discovered_at ?? null;
      return {
        id,
        name: endpointNameOf(raw),
        zoneId: endpointZoneIdOf(raw),
        zone: String(raw?.zone_name ?? t('Unassigned zone')),
        state: /fail|error|unreach/.test(probe) || scanErrors[id] ? 'bad' : discoveredAt ? 'ok' : 'none',
        newCount: Number(entry?.new_count ?? 0),
        total: Number(entry?.roots_count ?? 0),
        discoveredAt,
        raw
      };
    })
    .sort((a, b) => a.zone.localeCompare(b.zone) || a.name.localeCompare(b.name));

  $: current = servers.find((server) => server.id === currentId) ?? null;
  $: selectedByServer = [...selected.values()].reduce<Record<number, number>>((acc, folder) => {
    acc[folder.storage_endpoint_id] = (acc[folder.storage_endpoint_id] ?? 0) + 1;
    return acc;
  }, {});
  $: selectedServers = servers.filter((server) => selectedByServer[server.id]);
  $: badCount = servers.filter((server) => server.state === 'bad').length;
  $: forcedOpen = Boolean(serverQuery.trim()) || serverFilter !== 'all';
  $: visibleServers = servers
    .filter((server) => `${server.name} ${server.zone}`.toLowerCase().includes(serverQuery.trim().toLowerCase()))
    .filter((server) => serverFilter === 'all' || (serverFilter === 'selected' ? selectedByServer[server.id] : server.state === 'bad'));
  $: zones = [...new Set(visibleServers.map((server) => server.zone))].map((zone) => {
    const list = visibleServers.filter((server) => server.zone === zone);
    return { zone, list, picked: list.reduce((sum, server) => sum + (selectedByServer[server.id] ?? 0), 0) };
  });

  $: currentFolders = currentId ? foldersByServer[currentId] ?? [] : [];
  $: managedCount = currentFolders.filter((folder) => folder.managed).length;
  $: searchMode = Boolean(globalQuery.trim());
  $: rows = searchMode
    ? globalItems
    : currentFolders
        .filter((folder) => folderFilter === 'all' || (folderFilter === 'new' ? !folder.managed : folder.managed))
        .filter((folder) => `${folder.name} ${folder.root_path}`.toLowerCase().includes(folderQuery.trim().toLowerCase()));
  $: selectable = rows.filter((folder) => !folder.managed);
  $: allChecked = selectable.length > 0 && selectable.every((folder) => selected.has(keyOf(folder)));

  $: firstSelected = selected.values().next().value as Folder | undefined;
  $: void refreshPreview(firstSelected);
  $: guardiansInvalid = guardianIds.length > 0 && guardianIds.length < data.minGuardians;
  $: canAdd = selected.size > 0 && !guardiansInvalid && !running;

  const stateLabel = (server: Server) =>
    server.state === 'bad' ? t('Unreachable') : server.state === 'none' ? t('To analyse') : t('{count} new', { count: server.newCount });

  async function loadFolders(id: number, force = false) {
    if (foldersByServer[id] && !force) return;
    loadingFolders = true;
    loadError = '';
    try {
      const answer = await apiGetData<{ items: Folder[] }>(fetch, '/storage-roots/discovered', { storage_endpoint_id: id });
      foldersByServer = { ...foldersByServer, [id]: answer.items };
    } catch (error) {
      loadError = error instanceof Error ? error.message : t('Unable to read the folders of this server.');
    } finally {
      loadingFolders = false;
    }
  }

  function selectServer(server: Server) {
    currentId = server.id;
    openZones = { ...openZones, [server.zone]: true };
    globalQuery = '';
    folderQuery = '';
    anchor = null;
    void loadFolders(server.id);
  }

  async function rescan(server: Server) {
    const config = validateStorageEndpointProbeConfig(resolveStorageEndpointProbeConfig(server.raw as any), { label: server.name });
    if (!config.ok) {
      scanErrors = { ...scanErrors, [server.id]: t('This server has no account to read its folders: complete it in Servers.') };
      return;
    }
    scanning = { ...scanning, [server.id]: true };
    const { [server.id]: _gone, ...others } = scanErrors;
    scanErrors = others;
    try {
      const final: any = await runProbeWithPolling({
        fetchFn: fetch,
        request: buildStorageEndpointProbeRequestFromEndpoint(server.raw as any, { discover: true, timeoutSec: 30, uiOrigin: 'admin' }),
        intervalMs: 1500,
        maxAttempts: 80
      });
      if (!final.ok) throw new Error(humanizeFileServerMessage(t(String(final.errorMessage ?? 'Unable to read the folders of this server.'))));
      await syncStorageRootDiscoveryForEndpoint(fetch, server.id, final.result);
      // Connected, but the listing itself failed: an empty list would look like a server without folders
      if (parseStorageEndpointProbeRoots(final.result).length === 0 && final.result?.details?.discovery_complete === false) {
        throw new Error(t(String(final.result?.message ?? 'Unable to read the folders of this server.')));
      }
      await invalidate('app:storage-roots-add');
      await loadFolders(server.id, true);
    } catch (error) {
      scanErrors = { ...scanErrors, [server.id]: error instanceof Error ? error.message : t('Unable to read the folders of this server.') };
    } finally {
      scanning = { ...scanning, [server.id]: false };
    }
  }

  function onGlobalInput() {
    clearTimeout(searchTimer);
    anchor = null;
    const term = globalQuery.trim();
    if (!term) {
      globalItems = [];
      globalTotal = 0;
      searching = false;
      return;
    }
    searching = true;
    searchTimer = setTimeout(async () => {
      const ticket = ++searchTicket;
      try {
        const answer = await apiGetData<{ items: Folder[]; total: number }>(fetch, '/storage-roots/discovered', { q: term });
        if (ticket !== searchTicket) return;
        globalItems = answer.items;
        globalTotal = answer.total;
      } catch (error) {
        if (ticket === searchTicket) loadError = error instanceof Error ? error.message : t('The search failed.');
      } finally {
        if (ticket === searchTicket) searching = false;
      }
    }, SEARCH_DELAY_MS);
  }

  function clearSearch() {
    globalQuery = '';
    onGlobalInput();
  }

  function setChecked(folder: Folder, checked: boolean) {
    if (checked) selected.set(keyOf(folder), folder);
    else selected.delete(keyOf(folder));
  }

  function toggleRow(event: MouseEvent, folder: Folder, index: number) {
    const checked = !selected.has(keyOf(folder));
    if (event.shiftKey && anchor !== null) {
      const [low, high] = [Math.min(anchor, index), Math.max(anchor, index)];
      for (const row of rows.slice(low, high + 1)) if (!row.managed) setChecked(row, checked);
    } else {
      setChecked(folder, checked);
    }
    anchor = index;
    selected = selected;
  }

  function toggleAll() {
    const checked = !allChecked;
    for (const folder of selectable) setChecked(folder, checked);
    selected = selected;
  }

  function removeServer(id: number) {
    for (const [key, folder] of selected) if (folder.storage_endpoint_id === id) selected.delete(key);
    selected = selected;
  }

  async function refreshPreview(folder: Folder | undefined) {
    const key = folder ? keyOf(folder) : '';
    if (key === previewKey) return;
    previewKey = key;
    groupPreview = null;
    if (!folder) return;
    const server = servers.find((row) => row.id === folder.storage_endpoint_id);
    if (!server?.zoneId) return;
    const name = (perm: string) =>
      apiPostData<{ samAccountName: string }>(fetch, '/naming-policies/preview', {
        zone_id: server.zoneId,
        storage_endpoint_id: server.id,
        storage_root_path: folder.root_path,
        perm
      });
    try {
      const [read, write] = await Promise.all([name('READ'), name('WRITE')]);
      if (previewKey === key) groupPreview = { read: read.samAccountName, write: write.samAccountName };
    } catch {
      groupPreview = null; // Only an example: the folders can be added without it
    }
  }

  async function addFolders() {
    if (!canAdd) return;
    const list = [...selected.values()];
    running = true;
    finished = false;
    done = 0;
    total = list.length;
    createdIds = [];
    warnings = [];
    failures = [];
    try {
      for (let start = 0; start < list.length; start += BATCH_SIZE) {
        const batch = list.slice(start, start + BATCH_SIZE);
        const answer = await apiPostData<{
          created: Array<Folder & { id: number; warnings: string[] }>;
          failed: Failure[];
        }>(fetch, '/storage-roots/bulk', {
          items: batch.map(({ storage_endpoint_id, name, root_path }) => ({ storage_endpoint_id, name, root_path })),
          guardian_ids: guardianIds,
          tag_ids: tagIds
        });
        for (const row of answer.created) {
          selected.delete(keyOf(row));
          createdIds.push(row.id);
          warnings.push(...row.warnings.map((message) => `${row.name} : ${message}`));
        }
        failures.push(...answer.failed);
        done += batch.length;
        selected = selected;
      }
    } catch (error) {
      // What was not sent stays selected, so the same button resumes
      failures.push({ name: t('Interrupted'), root_path: '', message: error instanceof Error ? error.message : t('The server did not answer.') });
    }
    failures = failures;
    warnings = warnings;
    running = false;
    finished = true;
    foldersByServer = {};
    globalItems = [];
    globalQuery = '';
    await invalidate('app:storage-roots-add');
    if (currentId) await loadFolders(currentId, true);
  }

  // The folders are sent batch by batch from this page: leaving stops what is left, and forgets the selection
  beforeNavigate((navigation) => {
    if (navigation.type === 'leave') return;
    const question = running
      ? t('The folders are being added. Leave and stop what is left?')
      : selected.size > 0 && !finished
        ? t('Leave this page? The checked folders will be forgotten.')
        : null;
    if (question && !window.confirm(question)) navigation.cancel();
  });

  onMount(() => {
    // Opened from a server page: that server first
    const wanted = Number(new URL(window.location.href).searchParams.get('endpoint') ?? 0);
    const asked = servers.find((server) => server.id === wanted);
    if (asked) {
      selectServer(asked);
      return;
    }
    const first = servers.find((server) => server.state === 'ok' && server.newCount > 0) ?? servers.find((server) => server.state === 'ok') ?? servers[0];
    if (first) selectServer(first);
  });

  onDestroy(() => clearTimeout(searchTimer));
</script>

<section class="add-page">
  <header class="top">
    <div>
      <a class="crumb" href="/storage-roots"><i class="bi bi-chevron-left" aria-hidden="true"></i>{t('Folders')}</a>
      <h1>{t('Add folders to manage')}</h1>
    </div>
    <input
      class="b2s-input global"
      aria-label={t('Search all the servers')}
      placeholder={t('Search a folder on the {count} servers…', { count: servers.length })}
      bind:value={globalQuery}
      on:input={onGlobalInput}
    />
  </header>

  {#if servers.length === 0}
    <div class="empty-page">
      <strong>{t('No storage endpoint')}</strong>
      <p>{t('Add a file server first: its folders are listed here.')}</p>
      <a class="b2s-btn b2s-btn-primary" href="/admin/storage-endpoints">{t('Open the servers')}</a>
    </div>
  {:else}
    <div class="work">
      <section class="pane">
        <div class="pane-head">
          <input class="b2s-input" aria-label={t('Filter the servers')} placeholder={t('Filter the servers…')} bind:value={serverQuery} />
          <SegmentedFilter ariaLabel={t('Filter the servers')} bind:value={serverFilter} options={[
            { key: 'all', label: t('All'), count: servers.length },
            { key: 'selected', label: t('Checked'), count: selectedServers.length },
            { key: 'bad', label: t('Unreachable'), count: badCount }
          ]} />
        </div>
        <div class="scroll">
          {#each zones as group (group.zone)}
            {@const opened = forcedOpen || openZones[group.zone]}
            <button type="button" class="zone" aria-expanded={Boolean(opened)} on:click={() => (openZones = { ...openZones, [group.zone]: !openZones[group.zone] })}>
              <i class={`bi ${opened ? 'bi-chevron-down' : 'bi-chevron-right'}`} aria-hidden="true"></i>
              <span>{group.zone}</span>
              {#if group.picked}<span class="badge">{group.picked}</span>{/if}
              <small>{t('{count} servers', { count: group.list.length })}</small>
            </button>
            {#if opened}
              {#each group.list as server (server.id)}
                <button type="button" class="server" class:on={server.id === currentId && !searchMode} on:click={() => selectServer(server)}>
                  <span class={`dot dot--${server.state}`} aria-hidden="true"></span>
                  <span class="ell">{server.name}</span>
                  {#if selectedByServer[server.id]}
                    <span class="badge">{selectedByServer[server.id]}</span>
                  {:else}
                    <small>{stateLabel(server)}</small>
                  {/if}
                </button>
              {/each}
            {/if}
          {:else}
            <p class="note">{t('No server matches.')}</p>
          {/each}
        </div>
      </section>

      <section class="pane">
        <div class="pane-head">
          {#if searchMode}
            <div class="ctx">
              <h2>{searching ? t('Searching…') : t('{count} results', { count: globalTotal })}</h2>
              <small>{t('Folders not managed yet, on all the servers')}</small>
              <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm right" on:click={clearSearch}>{t('Clear')}</button>
            </div>
            {#if selectable.length}
              <div class="tools">
                <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" on:click={toggleAll}>
                  {allChecked ? t('Uncheck all') : t('Check the {count} shown', { count: selectable.length })}
                </button>
              </div>
            {/if}
          {:else if current}
            <div class="ctx">
              <h2>{current.name}</h2>
              <small class="ell">
                {t('Zone {name}', { name: current.zone })}{current.discoveredAt ? ` · ${t('analysed on {date}', { date: formatDateTime(current.discoveredAt) })}` : ''}
              </small>
              <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm right" disabled={scanning[current.id]} on:click={() => current && rescan(current)}>
                {scanning[current.id] ? t('Searching…') : t('Search the server again')}
              </button>
            </div>
            {#if currentFolders.length}
              <div class="tools">
                <input class="b2s-input" aria-label={t('Filter this server')} placeholder={t('Filter this server…')} bind:value={folderQuery} />
                <SegmentedFilter ariaLabel={t('Filter by state')} bind:value={folderFilter} options={[
                  { key: 'new', label: t('New'), count: currentFolders.length - managedCount },
                  { key: 'managed', label: t('Managed'), count: managedCount },
                  { key: 'all', label: t('All'), count: currentFolders.length }
                ]} />
                <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" disabled={!selectable.length} on:click={toggleAll}>
                  {allChecked ? t('Uncheck all') : t('Check {count}', { count: selectable.length })}
                </button>
              </div>
            {/if}
          {/if}
        </div>

        <div class="scroll">
          {#if loadError}<div class="pad"><InlineAlert tone="error">{loadError}</InlineAlert></div>{/if}
          {#if !searchMode && current && scanErrors[current.id]}<div class="pad"><InlineAlert tone="error">{scanErrors[current.id]}</InlineAlert></div>{/if}

          {#each rows as folder, index (keyOf(folder))}
            <button type="button" class="folder" class:folder--search={searchMode} class:sel={selected.has(keyOf(folder))} disabled={folder.managed} title={folder.root_path} on:click={(event) => toggleRow(event, folder, index)}>
              <span class="check" aria-hidden="true">{#if selected.has(keyOf(folder))}<i class="bi bi-check-lg"></i>{/if}</span>
              <span class="ell name">{folder.name}</span>
              {#if searchMode}<span class="ell mono muted">{folder.storage_endpoint_name}</span>{/if}
              <span class="ell mono muted">{folder.root_path}</span>
              <small>{folder.managed ? t('Already managed') : ''}</small>
            </button>
          {:else}
            {#if searchMode}
              {#if !searching}<p class="note">{t('No folder matches this search.')}</p>{/if}
            {:else if loadingFolders}
              <p class="note">{t('Loading…')}</p>
            {:else if current && !currentFolders.length}
              <div class="empty">
                <strong>{current.state === 'bad' ? t('Unreachable') : t('Never analysed')}</strong>
                <span>{current.state === 'bad' ? t('Check that the server is started and that its firewall allows it, then search again.') : t('Search this server to list its folders.')}</span>
                <button type="button" class="b2s-btn b2s-btn-primary b2s-btn-sm" disabled={scanning[current.id]} on:click={() => current && rescan(current)}>
                  {scanning[current.id] ? t('Searching…') : t('Search the folders')}
                </button>
              </div>
            {:else if currentFolders.length}
              <p class="note">{t('No folder matches this search.')}</p>
            {/if}
          {/each}
          {#if searchMode && globalTotal > globalItems.length}
            <p class="note">{t('The first {shown} results are shown: refine the search to reach the others.', { shown: globalItems.length })}</p>
          {/if}
        </div>
        <div class="tip"><kbd>{t('Shift')}</kbd> + {t('click checks a whole range. The selection stays when you change server.')}</div>
      </section>

      <aside class="pane">
        {#if running || finished}
          <div class="panel-body">
            <h2>{running ? t('Adding…') : t('Folders added')}</h2>
            <div class="bar"><i style={`width:${total ? (100 * done) / total : 0}%`}></i></div>
            <span class="num">{t('{done} of {total} folders', { done, total })}</span>
            {#if running}<small class="muted">{t('Stay on this page until the end.')}</small>{/if}
            {#if finished}
              <InlineAlert tone={failures.length ? 'warning' : 'success'}>
                {t('{created} added, {failed} refused.', { created: createdIds.length, failed: failures.length })}
              </InlineAlert>
              {#if createdIds.length}
                <small class="muted">{t('The worker now checks each folder and reads its permissions: they show « To verify » until then.')}</small>
              {/if}
              {#if !guardianIds.length && createdIds.length}
                <small class="muted">{t('No guardian chosen: only administrators can approve the requests for now.')}</small>
              {/if}
            {/if}
            {#if failures.length}
              <div class="issues">
                <strong>{t('Refused: they stay checked')}</strong>
                {#each failures as failure}<small><b>{failure.name}</b> {humanizeFileServerMessage(t(failure.message))}</small>{/each}
              </div>
            {/if}
            {#if warnings.length}
              <div class="issues">
                <strong>{t('Added, governance to complete')}</strong>
                {#each warnings.slice(0, 10) as warning}<small>{warning}</small>{/each}
                {#if warnings.length > 10}<small>{t('and {count} others', { count: warnings.length - 10 })}</small>{/if}
              </div>
            {/if}
          </div>
          {#if finished}
            <div class="panel-foot">
              <button type="button" class="b2s-btn b2s-btn-primary wide" on:click={() => { finished = false; guardianIds = []; tagIds = []; }}>{t('Add other folders')}</button>
              <a class="b2s-btn b2s-btn-secondary wide" href={createdIds[0] ? `/storage-roots?selected=${createdIds[0]}` : '/storage-roots'}>{t('See the folders')}</a>
            </div>
          {/if}
        {:else}
          <div class="panel-body">
            <h2>{t('Your selection')}</h2>
            <div><span class="big">{selected.size}</span> <span class="muted">{selected.size <= 1 ? t('folder selected') : t('folders on {count} servers', { count: selectedServers.length })}</span></div>
            {#if selected.size}
              <div>
                {#each selectedServers.slice(0, 5) as server (server.id)}
                  <div class="by">
                    <button type="button" class="ell link" on:click={() => selectServer(server)}>{server.name}</button>
                    <span class="badge">{selectedByServer[server.id]}</span>
                    <button type="button" class="x" aria-label={t('Remove {name}', { name: server.name })} on:click={() => removeServer(server.id)}>×</button>
                  </div>
                {/each}
                {#if selectedServers.length > 5}<small class="muted">{t('and {count} other servers', { count: selectedServers.length - 5 })}</small>{/if}
              </div>
              {#if groupPreview}
                <div class="groups">
                  <strong>{t('Groups prepared (example: {name})', { name: firstSelected?.name ?? '' })}</strong>
                  <div><span class="tag tag--read">{t('Read')}</span><span class="mono">{groupPreview.read}</span></div>
                  <div><span class="tag tag--write">{t('Write')}</span><span class="mono">{groupPreview.write}</span></div>
                </div>
              {/if}
              <details>
                <summary>{t('Guardians and tags (optional)')}</summary>
                <div class="gov">
                  <GovernancePicker id="add-guardians" label={t('Guardians')} placeholder={t('Search a person…')} options={data.people} bind:selected={guardianIds} />
                  {#if guardiansInvalid}<small class="field-error">{t('Choose at least {count} guardians, or none for now.', { count: data.minGuardians })}</small>{/if}
                  <GovernancePicker id="add-tags" label={t('Tags')} placeholder={t('Search a tag…')} options={data.tags} bind:selected={tagIds} />
                  <small class="muted">{t('Applied to all the checked folders.')}</small>
                </div>
              </details>
            {:else}
              <small class="muted">{t('Check folders, on one or several servers.')}</small>
            {/if}
          </div>
          <div class="panel-foot">
            <small class="muted">{t('No permission changes now: they apply at the first approved request.')}</small>
            <button type="button" class="b2s-btn b2s-btn-primary wide" disabled={!canAdd} on:click={addFolders}>
              {selected.size === 0 ? t('Add folders') : selected.size === 1 ? t('Add 1 folder') : t('Add {count} folders', { count: selected.size })}
            </button>
          </div>
        {/if}
      </aside>
    </div>
  {/if}
</section>

<style>
  .add-page { padding: 20px 24px; }
  .top { display: flex; align-items: flex-end; gap: 24px; margin-bottom: 14px; }
  .crumb { display: inline-flex; align-items: center; gap: 4px; color: var(--b2s-color-text-muted); font-size: var(--b2s-text-sm); text-decoration: none; }
  .crumb:hover { color: var(--b2s-color-text); }
  h1 { margin: 2px 0 0; font-size: var(--b2s-fs-page-title); color: var(--b2s-color-heading); }
  h2 { margin: 0; font-size: var(--b2s-fs-md); font-weight: 600; color: var(--b2s-color-heading); white-space: nowrap; }
  .global { flex: 1; max-width: 560px; margin-left: auto; height: 42px; }

  .work { display: grid; grid-template-columns: 286px minmax(0, 1fr) 304px; gap: 14px; height: calc(100vh - 120px); min-height: 520px; }
  .pane { display: flex; flex-direction: column; min-height: 0; overflow: hidden; background: var(--b2s-color-surface); border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-lg); box-shadow: var(--b2s-shadow-sm); }
  .pane-head { display: flex; flex-direction: column; gap: 9px; padding: 13px 14px; border-bottom: 1px solid var(--b2s-color-border); }
  .scroll { flex: 1; min-height: 0; overflow: auto; }
  .pad { padding: 10px 14px; }
  .note { margin: 0; padding: 18px; color: var(--b2s-color-text-muted); font-size: var(--b2s-font-micro); text-align: center; }


  .zone { position: sticky; top: 0; z-index: 1; display: flex; align-items: center; gap: 6px; width: 100%; padding: 8px 14px; border: 0; border-bottom: 1px solid var(--b2s-color-border); background: var(--b2s-color-surface-soft); font-size: var(--b2s-text-sm); font-weight: 600; text-align: left; cursor: pointer; }
  .zone small { margin-left: auto; font-weight: 400; color: var(--b2s-color-text-muted); }
  .server { display: grid; grid-template-columns: 8px minmax(0, 1fr) auto; gap: 9px; align-items: center; width: 100%; padding: 8px 14px; border: 0; border-bottom: 1px solid var(--b2s-color-border); background: var(--b2s-color-surface); text-align: left; font-size: var(--b2s-text-sm); cursor: pointer; }
  .server:hover { background: var(--b2s-color-surface-soft); }
  .server.on { background: var(--b2s-accent-soft); box-shadow: inset 3px 0 0 var(--b2s-accent-strong); }
  .server small { color: var(--b2s-color-text-muted); font-size: var(--b2s-font-micro); }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--b2s-color-border-mid); }
  .dot--ok { background: var(--b2s-color-success-strong); }
  .dot--bad { background: var(--b2s-color-danger-strong); }
  .badge { min-width: 20px; padding: 0 6px; border-radius: var(--b2s-radius-pill); background: var(--b2s-accent); color: var(--b2s-on-accent); font-size: var(--b2s-font-micro); font-weight: 600; text-align: center; }

  .ctx { display: flex; align-items: center; gap: 10px; min-width: 0; }
  .ctx small { color: var(--b2s-color-text-muted); font-size: var(--b2s-font-micro); }
  .right { margin-left: auto; flex: none; }
  .tools { display: flex; align-items: center; gap: 8px; }
  .tools .b2s-input { flex: 1; min-width: 0; }
  .tools .b2s-btn { flex: none; }

  .folder { display: grid; grid-template-columns: 20px minmax(0, 1fr) minmax(0, 1fr) 84px; gap: 12px; align-items: center; width: 100%; padding: 7px 14px; border: 0; border-bottom: 1px solid var(--b2s-color-border); background: var(--b2s-color-surface); text-align: left; font-size: var(--b2s-text-sm); cursor: pointer; user-select: none; }
  .folder--search { grid-template-columns: 20px minmax(0, 1fr) 128px minmax(0, 1fr) 84px; }
  .folder:hover:not(:disabled) { background: var(--b2s-color-surface-soft); }
  .folder.sel { background: var(--b2s-accent-soft); }
  .folder:disabled { color: var(--b2s-color-text-muted); cursor: default; }
  .folder small { color: var(--b2s-color-text-muted); font-size: var(--b2s-font-micro); }
  .name { font-weight: 500; }
  .check { display: grid; place-items: center; width: 18px; height: 18px; border: 1.5px solid var(--b2s-color-border-mid); border-radius: 5px; font-size: 12px; }
  .sel .check { background: var(--b2s-accent-strong); border-color: var(--b2s-accent-strong); color: var(--b2s-on-accent); }
  .folder:disabled .check { background: var(--b2s-color-neutral-soft); }
  .ell { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .mono { font-family: var(--b2s-font-mono); font-size: var(--b2s-font-micro); }
  .muted { color: var(--b2s-color-text-muted); font-size: var(--b2s-font-micro); }
  .empty { display: flex; flex-direction: column; align-items: center; gap: 9px; margin: 18px; padding: 26px; border-radius: var(--b2s-radius-md); background: var(--b2s-color-surface-soft); font-size: var(--b2s-text-sm); text-align: center; }
  .tip { padding: 7px 14px; border-top: 1px solid var(--b2s-color-border); background: var(--b2s-color-surface-soft); color: var(--b2s-color-text-muted); font-size: var(--b2s-font-micro); }
  kbd { padding: 0 5px; color: var(--b2s-color-text); border: 1px solid var(--b2s-color-border-mid); border-radius: 4px; background: var(--b2s-color-surface); font: 11px var(--b2s-font-mono); }

  .panel-body { flex: 1; min-height: 0; overflow: auto; display: flex; flex-direction: column; gap: 12px; padding: 15px; }
  .panel-foot { display: flex; flex-direction: column; gap: 7px; padding: 13px 15px; border-top: 1px solid var(--b2s-color-border); }
  .wide { width: 100%; justify-content: center; text-decoration: none; }
  .big { font-size: 32px; font-weight: 600; line-height: 1; font-variant-numeric: tabular-nums; }
  .num { font-variant-numeric: tabular-nums; font-size: var(--b2s-text-sm); }
  .by { display: grid; grid-template-columns: minmax(0, 1fr) auto 18px; gap: 6px; align-items: center; padding: 3px 0; font-size: var(--b2s-text-sm); }
  .link { padding: 0; border: 0; background: none; text-align: left; cursor: pointer; }
  .x { padding: 0; border: 0; background: none; color: var(--b2s-color-text-muted); font-size: 15px; cursor: pointer; }
  .x:hover { color: var(--b2s-color-danger-strong); }
  .groups { display: flex; flex-direction: column; gap: 6px; padding: 10px; border-radius: var(--b2s-radius-md); background: var(--b2s-color-surface-soft); font-size: var(--b2s-font-micro); }
  .groups div { display: flex; align-items: center; gap: 7px; min-width: 0; }
  .groups .mono { overflow-wrap: anywhere; }
  .tag { padding: 1px 8px; border-radius: var(--b2s-radius-pill); font-weight: 500; }
  .tag--read { background: var(--b2s-color-info-soft); color: var(--b2s-color-info-strong); }
  .tag--write { background: var(--b2s-color-warning-soft); color: var(--b2s-color-warning-strong); }
  details { padding: 9px 12px; border: 1px solid var(--b2s-color-border); border-radius: var(--b2s-radius-md); }
  summary { font-size: var(--b2s-text-sm); font-weight: 500; cursor: pointer; }
  .gov { display: flex; flex-direction: column; gap: 10px; margin-top: 10px; }
  .field-error { color: var(--b2s-color-danger-strong); font-size: var(--b2s-font-micro); }
  .bar { height: 7px; overflow: hidden; border-radius: var(--b2s-radius-pill); background: var(--b2s-color-neutral-soft); }
  .bar i { display: block; height: 100%; background: var(--b2s-accent-strong); transition: width 0.2s; }
  .issues { display: flex; flex-direction: column; gap: 5px; font-size: var(--b2s-font-micro); }
  .issues small { color: var(--b2s-color-text-muted); overflow-wrap: anywhere; }
  .empty-page { display: flex; flex-direction: column; align-items: center; gap: 10px; padding: 60px; background: var(--b2s-color-surface); border-radius: var(--b2s-radius-lg); }
  .empty-page p { margin: 0; color: var(--b2s-color-text-muted); }
</style>
