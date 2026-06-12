<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import EntityActionButton from '$lib/components/common/EntityActionButton.svelte';
  import type { AddRootEndpoint, AddRootFolder, AddRootZone } from './add-storage-root.types';

  export let open = false;
  export let zones: AddRootZone[] = [];
  export let selectedZoneId: string | number | null = null;
  export let selectedEndpointId: string | number | null = null;
  export let selectedFolderId: string | number | null = null;
  export let selectedFolderIds: Array<string | number> = [];
  export let managedRootKeys: string[] = [];
  export let loading = false;

  const dispatch = createEventDispatcher<{
    close: void;
    selectZone: { zoneId: string | number };
    selectEndpoint: { zoneId: string | number; endpointId: string | number };
    triggerEndpointDiscovery: { zoneId: string | number; endpointId: string | number };
    selectFolder: { folderId: string | number };
    selectFolders: { folderIds: Array<string | number> };
    create: { inheritGovernance: boolean; folderIds: Array<string | number> };
  }>();

  let search = '';
  let currentStep = 1;
  let expandedByZoneId: Record<string, boolean> = {};
  let wasOpen = false;
  let inheritGovernance = true;
  let folderSearch = '';
  let folderFilter: 'all' | 'new' | 'managed' | 'alerts' = 'all';
  let folderSort = 'name-asc';

  const fmt = (iso?: string | null) => {
    const value = String(iso ?? '').trim();
    if (!value) return '—';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '—';
    return date.toLocaleString('fr-FR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const normalized = (value: unknown) => String(value ?? '').trim().toLowerCase();
  const pathKey = (endpointId: unknown, rootPath: unknown) =>
    `${Number(endpointId ?? 0)}:${String(rootPath ?? '')
      .trim()
      .replace(/\\/g, '/')
      .replace(/\/+$/, '')
      .toLowerCase()}`;

  $: if (open && !wasOpen) {
    currentStep = 1;
    inheritGovernance = true;
    folderSearch = '';
    folderFilter = 'all';
    folderSort = 'name-asc';
    expandedByZoneId = zones.reduce<Record<string, boolean>>((acc, zone) => {
      acc[String(zone.id)] = true;
      return acc;
    }, {});
  }

  $: wasOpen = open;

  $: selectedZone = zones.find((zone) => String(zone.id) === String(selectedZoneId ?? '')) ?? null;
  $: selectedEndpoint =
    (selectedZone?.endpoints ?? []).find((endpoint) => String(endpoint.id) === String(selectedEndpointId ?? '')) ??
    zones.flatMap((zone) => zone.endpoints ?? []).find((endpoint) => String(endpoint.id) === String(selectedEndpointId ?? '')) ??
    null;
  $: selectedFolders = Array.isArray(selectedEndpoint?.discoveredFolders) ? selectedEndpoint.discoveredFolders : [];
  $: effectiveSelectedFolderIds = selectedFolderIds.length > 0 ? selectedFolderIds : selectedFolderId ? [selectedFolderId] : [];
  $: selectedFolder =
    selectedFolders.find((folder) => String(folder.id) === String(effectiveSelectedFolderIds[0] ?? '')) ??
    zones.flatMap((zone) => zone.discoveredFolders ?? []).find((folder) => String(folder.id) === String(effectiveSelectedFolderIds[0] ?? '')) ??
    null;
  $: selectedFolderRows = selectedFolders.filter((folder) =>
    effectiveSelectedFolderIds.some((folderId) => String(folderId) === String(folder.id))
  );
  $: lastRefreshAt =
    selectedEndpoint?.lastRefreshAt ??
    zones.flatMap((zone) => zone.endpoints ?? []).map((endpoint) => endpoint.lastRefreshAt).filter(Boolean)[0] ??
    selectedEndpoint?.lastProbeAt ??
    null;

  function visibleEndpoints(zone: AddRootZone): AddRootEndpoint[] {
    const query = normalized(search);
    const endpoints = zone.endpoints ?? [];
    if (!query) return endpoints;
    const zoneMatches = normalized(zone.name).includes(query);
    if (zoneMatches) return endpoints;
    return endpoints.filter((endpoint) => normalized(endpoint.name).includes(query) || normalized(endpoint.host).includes(query));
  }

  function filteredZones(): AddRootZone[] {
    return zones.filter((zone) => visibleEndpoints(zone).length > 0 || normalized(zone.name).includes(normalized(search)));
  }

  function toggleZone(zoneId: string | number) {
    const key = String(zoneId);
    expandedByZoneId = { ...expandedByZoneId, [key]: !(expandedByZoneId[key] ?? true) };
  }

  function selectEndpoint(zone: AddRootZone, endpoint: AddRootEndpoint) {
    dispatch('selectEndpoint', { zoneId: zone.id, endpointId: endpoint.id });
  }

  function selectFolder(folder: AddRootFolder) {
    dispatch('selectFolder', { folderId: folder.id });
  }

  function isManagedFolder(folder: AddRootFolder): boolean {
    return managedRootKeys.includes(pathKey(folder.endpointId, folder.rootPath));
  }

  function folderHasAlert(_folder: AddRootFolder): boolean {
    return endpointState(selectedEndpoint).tone === 'danger';
  }

  function folderTone(folder: AddRootFolder): 'new' | 'managed' | 'alert' {
    if (isManagedFolder(folder)) return 'managed';
    if (folderHasAlert(folder)) return 'alert';
    return 'new';
  }

  $: folderCounts = selectedFolders.reduce(
    (acc, folder) => {
      acc.all += 1;
      if (isManagedFolder(folder)) acc.managed += 1;
      else acc.new += 1;
      if (folderHasAlert(folder)) acc.alerts += 1;
      return acc;
    },
    { all: 0, new: 0, managed: 0, alerts: 0 }
  );

  $: eligibleFolders = selectedFolders.filter((folder) => !isManagedFolder(folder));
  $: visibleFolders = selectedFolders
    .filter((folder) => {
      const query = normalized(folderSearch);
      if (query && !normalized(folder.folderName).includes(query) && !normalized(folder.rootPath).includes(query)) return false;
      if (folderFilter === 'new') return !isManagedFolder(folder);
      if (folderFilter === 'managed') return isManagedFolder(folder);
      if (folderFilter === 'alerts') return folderHasAlert(folder);
      return true;
    })
    .sort((a, b) => {
      if (folderSort === 'path-asc') return String(a.rootPath ?? '').localeCompare(String(b.rootPath ?? ''), 'en');
      return String(a.folderName ?? '').localeCompare(String(b.folderName ?? ''), 'en');
    });

  function setSelectedFolderIds(folderIds: Array<string | number>) {
    const next = folderIds.filter((folderId, index, rows) => rows.findIndex((candidate) => String(candidate) === String(folderId)) === index);
    dispatch('selectFolders', { folderIds: next });
    if (next[0] !== undefined) {
      dispatch('selectFolder', { folderId: next[0] });
    }
  }

  function toggleFolder(folder: AddRootFolder) {
    if (isManagedFolder(folder)) return;
    const exists = effectiveSelectedFolderIds.some((folderId) => String(folderId) === String(folder.id));
    setSelectedFolderIds(
      exists
        ? effectiveSelectedFolderIds.filter((folderId) => String(folderId) !== String(folder.id))
        : [...effectiveSelectedFolderIds, folder.id]
    );
  }

  function selectAllEligible() {
    const allSelected = eligibleFolders.length > 0 && eligibleFolders.every((folder) =>
      effectiveSelectedFolderIds.some((folderId) => String(folderId) === String(folder.id))
    );
    setSelectedFolderIds(allSelected ? [] : eligibleFolders.map((folder) => folder.id));
  }

  function close() {
    dispatch('close');
  }

  function runDiscovery(endpoint = selectedEndpoint) {
    if (!selectedZoneId || !endpoint) return;
    dispatch('triggerEndpointDiscovery', { zoneId: selectedZoneId, endpointId: endpoint.id });
  }

  function refreshAllEndpoints() {
    for (const zone of zones) {
      for (const endpoint of zone.endpoints ?? []) {
        if (!endpoint.refreshing) {
          dispatch('triggerEndpointDiscovery', { zoneId: zone.id, endpointId: endpoint.id });
        }
      }
    }
  }

  function endpointState(endpoint: AddRootEndpoint | null): {
    label: string;
    tone: 'success' | 'warning' | 'danger' | 'muted';
  } {
    const raw = normalized(endpoint?.status ?? endpoint?.lastProbeStatus ?? endpoint?.refreshStatus);
    if (raw === 'disabled' || raw === 'inactive') return { label: 'Disabled', tone: 'muted' };
    if (raw.includes('fail') || raw.includes('unreach') || raw.includes('error')) return { label: 'Unreachable', tone: 'danger' };
    if (raw === 'running') return { label: 'Running', tone: 'warning' };
    if (raw.includes('success') || raw.includes('ok') || raw.includes('reach') || raw.includes('healthy')) {
      return { label: 'Reachable', tone: 'success' };
    }
    if (endpoint?.refreshStatus === 'success' || endpoint?.discoveryCount > 0) return { label: 'Reachable', tone: 'success' };
    return { label: 'Unknown', tone: 'muted' };
  }

  function statusDotClass(endpoint: AddRootEndpoint | null): string {
    return `sr-add-dot sr-add-dot--${endpointState(endpoint).tone}`;
  }

  function goNext() {
    if (currentStep === 1 && selectedEndpoint) {
      currentStep = 2;
      return;
    }
    if (currentStep === 2 && selectedFolderRows.length > 0) {
      currentStep = 3;
    }
  }

  function goBack() {
    currentStep = Math.max(1, currentStep - 1);
  }

  function create() {
    dispatch('create', { inheritGovernance, folderIds: effectiveSelectedFolderIds });
  }
</script>

{#if open}
  <div class="sr-add-backdrop" aria-hidden="true"></div>
  <div class="sr-add-drawer" role="dialog" aria-modal="true" aria-labelledby="sr-add-title">
    <header class="sr-add-header">
      <div class="sr-add-title-row">
        <h2 id="sr-add-title">Add storage roots</h2>
        <button type="button" class="sr-add-icon-btn" aria-label="Close" on:click={close}>
          <i class="bi bi-x-lg" aria-hidden="true"></i>
        </button>
      </div>

      <ol class="sr-add-stepper" aria-label="Creation steps">
        <li class:active={currentStep === 1} class:done={currentStep > 1}>
          <span>{#if currentStep > 1}<i class="bi bi-check-lg" aria-hidden="true"></i>{:else}1{/if}</span>
          <div>
            <strong>Select source</strong>
            <small>Choose zone and endpoint</small>
          </div>
        </li>
        <li class:active={currentStep === 2} class:done={currentStep > 2}>
          <span>{#if currentStep > 2}<i class="bi bi-check-lg" aria-hidden="true"></i>{:else}2{/if}</span>
          <div>
            <strong>Select storage roots</strong>
            <small>Discover and select folders</small>
          </div>
        </li>
        <li class:active={currentStep === 3}>
          <span>3</span>
          <div>
            <strong>Review & import</strong>
            <small>Set governance and confirm</small>
          </div>
        </li>
      </ol>
    </header>

    <div class="sr-add-body">
      <aside class="sr-add-source-panel">
        {#if currentStep === 1}
          <label class="sr-add-search">
            <i class="bi bi-search" aria-hidden="true"></i>
            <input
              type="search"
              bind:value={search}
              placeholder="Search zones or endpoints..."
              aria-label="Search zones or endpoints"
            />
          </label>

          <div class="sr-add-zone-list">
            {#if filteredZones().length === 0}
              <div class="sr-add-empty-compact">No source matches your search.</div>
            {:else}
              {#each filteredZones() as zone (zone.id)}
                <article class="sr-add-zone">
                  <button
                    type="button"
                    class="sr-add-zone-title"
                    aria-expanded={expandedByZoneId[String(zone.id)] ?? true}
                    on:click={() => toggleZone(zone.id)}
                  >
                    <i class={`bi ${expandedByZoneId[String(zone.id)] ?? true ? 'bi-caret-down-fill' : 'bi-caret-right-fill'}`} aria-hidden="true"></i>
                    <i class="bi bi-folder2" aria-hidden="true"></i>
                    <span>{zone.name}</span>
                  </button>

                  {#if expandedByZoneId[String(zone.id)] ?? true}
                    <div class="sr-add-endpoints">
                      {#each visibleEndpoints(zone) as endpoint (endpoint.id)}
                        {@const state = endpointState(endpoint)}
                        <button
                          type="button"
                          class="sr-add-endpoint-card"
                          class:selected={String(endpoint.id) === String(selectedEndpointId ?? '')}
                          on:click={() => selectEndpoint(zone, endpoint)}
                        >
                          <i class="bi bi-hdd-network sr-add-endpoint-icon" aria-hidden="true"></i>
                          <span class="sr-add-endpoint-main">
                            <strong>{endpoint.name}</strong>
                            <small><span class={statusDotClass(endpoint)}></span>{state.label}</small>
                            <em>{endpoint.discoveryCount} {endpoint.discoveryCount === 1 ? 'root' : 'roots'} discovered</em>
                          </span>
                          <i class="bi bi-chevron-right sr-add-chevron" aria-hidden="true"></i>
                        </button>
                      {/each}
                    </div>
                  {/if}
                </article>
              {/each}
            {/if}
          </div>

          <footer class="sr-add-source-footer">
            <button type="button" class="sr-add-refresh-all" disabled={loading} on:click={refreshAllEndpoints}>
              <i class="bi bi-arrow-clockwise" aria-hidden="true"></i>
              Refresh all endpoints
            </button>
            <div class="sr-add-last-refresh">
              <span class="sr-add-dot sr-add-dot--success"></span>
              Last refresh: {fmt(lastRefreshAt)}
            </div>
          </footer>
        {:else if currentStep === 2}
          {@const state = endpointState(selectedEndpoint)}
          <label class="sr-add-search">
            <i class="bi bi-search" aria-hidden="true"></i>
            <input
              type="search"
              bind:value={folderSearch}
              placeholder="Search discovered roots..."
              aria-label="Search discovered roots"
            />
          </label>

          <div class="sr-add-endpoint-summary">
            <div class="sr-add-endpoint-summary-head">
              <span class="sr-add-server-icon sr-add-server-icon--sm"><i class="bi bi-hdd-network" aria-hidden="true"></i></span>
              <div>
                <h3>{selectedEndpoint?.name ?? 'Endpoint'}</h3>
                <div class="sr-add-pills">
                  <span>Zone {selectedEndpoint?.zoneName ?? selectedZone?.name ?? '—'}</span>
                  <span>{selectedEndpoint?.protocol ?? '—'}</span>
                </div>
              </div>
              <span class={`sr-add-status sr-add-status--${state.tone}`}>{state.label}</span>
            </div>

            <div class="sr-add-sidebar-facts">
              <div>
                <i class="bi bi-clock" aria-hidden="true"></i>
                <span>Last discovery</span>
                <strong>{fmt(selectedEndpoint?.lastRefreshAt ?? selectedEndpoint?.lastProbeAt)}</strong>
              </div>
              <div>
                <i class="bi bi-folder2-open" aria-hidden="true"></i>
                <span>{selectedEndpoint?.discoveryCount ?? 0} discovered roots</span>
              </div>
            </div>

            <div class="sr-add-filter-chips" aria-label="Discovery filters">
              <button type="button" class:active={folderFilter === 'all'} on:click={() => (folderFilter = 'all')}>All <span>{folderCounts.all}</span></button>
              <button type="button" class:active={folderFilter === 'new'} on:click={() => (folderFilter = 'new')}>New <span>{folderCounts.new}</span></button>
              <button type="button" class:active={folderFilter === 'managed'} on:click={() => (folderFilter = 'managed')}>Already managed <span>{folderCounts.managed}</span></button>
              <button type="button" class:active={folderFilter === 'alerts'} on:click={() => (folderFilter = 'alerts')}>Alerts <span>{folderCounts.alerts}</span></button>
            </div>

            <button type="button" class="sr-add-refresh-all" disabled={Boolean(selectedEndpoint?.refreshing) || loading} on:click={() => runDiscovery()}>
              <i class="bi bi-arrow-clockwise" aria-hidden="true"></i>
              Run discovery again
            </button>

            <p class="sr-add-sidebar-note">
              <i class="bi bi-info-circle" aria-hidden="true"></i>
              Folders that are already managed cannot be selected again.
            </p>
          </div>
        {:else}
          {@const state = endpointState(selectedEndpoint)}
          <div class="sr-add-review-sidebar">
            <section class="sr-add-review-side-card">
              <h3>Selected endpoint</h3>
              <div class="sr-add-endpoint-summary-head">
                <span class="sr-add-server-icon sr-add-server-icon--sm"><i class="bi bi-hdd-network" aria-hidden="true"></i></span>
                <div>
                  <h4>{selectedEndpoint?.name ?? 'Endpoint'}</h4>
                  <div class="sr-add-pills">
                    <span>Zone {selectedEndpoint?.zoneName ?? selectedZone?.name ?? '—'}</span>
                    <span>{selectedEndpoint?.protocol ?? '—'}</span>
                  </div>
                </div>
                <span class={`sr-add-status sr-add-status--${state.tone}`}>{state.label}</span>
              </div>

              <div class="sr-add-sidebar-facts sr-add-sidebar-facts--review">
                <div>
                  <i class="bi bi-clock" aria-hidden="true"></i>
                  <span>Last discovery</span>
                  <strong>{fmt(selectedEndpoint?.lastRefreshAt ?? selectedEndpoint?.lastProbeAt)}</strong>
                </div>
                <div>
                  <i class="bi bi-folder2" aria-hidden="true"></i>
                  <span>Base path</span>
                  <strong>{selectedEndpoint?.basePath || '—'}</strong>
                </div>
                <div>
                  <i class="bi bi-folder2-open" aria-hidden="true"></i>
                  <span>Discovered roots</span>
                  <strong>{selectedEndpoint?.discoveryCount ?? 0}</strong>
                </div>
              </div>
            </section>

            <section class="sr-add-review-side-card sr-add-review-side-card--roots">
              <h3>Selected storage roots</h3>
              <p>{selectedFolderRows.length} selected</p>
              <div class="sr-add-review-side-roots">
                {#each selectedFolderRows as folder (folder.id)}
                  <div>
                    <i class="bi bi-folder2-open" aria-hidden="true"></i>
                    <span>
                      <strong>{folder.folderName}</strong>
                      <small>{folder.rootPath}</small>
                    </span>
                    <em>New</em>
                  </div>
                {/each}
              </div>
            </section>
          </div>
        {/if}
      </aside>

      <main class="sr-add-main" class:sr-add-main--step2={currentStep === 2} class:sr-add-main--step3={currentStep === 3}>
        {#if currentStep === 1}
          {#if selectedEndpoint}
            {@const state = endpointState(selectedEndpoint)}
            <section class="sr-add-selected">
              <div class="sr-add-selected-head">
                <div>
                  <p class="sr-add-kicker">Selected endpoint</p>
                  <div class="sr-add-endpoint-title">
                    <span class="sr-add-server-icon"><i class="bi bi-hdd-network" aria-hidden="true"></i></span>
                    <div>
                      <h3>{selectedEndpoint.name}</h3>
                      <div class="sr-add-pills">
                        <span>Zone {selectedEndpoint.zoneName ?? selectedZone?.name ?? '—'}</span>
                        <span>Protocol {selectedEndpoint.protocol ?? '—'}</span>
                      </div>
                    </div>
                  </div>
                </div>
                <span class={`sr-add-status sr-add-status--${state.tone}`}>{state.label}</span>
              </div>

              <div class="sr-add-metrics" aria-label="Endpoint summary">
                <div>
                  <small>Last discovery</small>
                  <strong>{fmt(selectedEndpoint.lastRefreshAt ?? selectedEndpoint.lastProbeAt)}</strong>
                </div>
                <div>
                  <small>Base path</small>
                  <strong>{selectedEndpoint.basePath || '—'}</strong>
                </div>
                <div>
                  <small>Discovered roots</small>
                  <strong>{selectedEndpoint.discoveryCount}</strong>
                </div>
                <div>
                  <small>Status</small>
                  <strong><span class={statusDotClass(selectedEndpoint)}></span>{state.label}</strong>
                </div>
              </div>

              <section class="sr-add-next">
                <h4>What happens next?</h4>
                <p>We will scan the configured base paths on this endpoint and list eligible folders that can be managed as storage roots.</p>
                <ul>
                  <li><i class="bi bi-check-circle-fill" aria-hidden="true"></i>You will be able to review and select folders.</li>
                  <li><i class="bi bi-check-circle-fill" aria-hidden="true"></i>No storage root will be created until you confirm.</li>
                </ul>
              </section>

              <section class="sr-add-discovery-card">
                <span><i class="bi bi-info-circle" aria-hidden="true"></i></span>
                {#if selectedEndpoint.discoveryCount > 0}
                  <h4>{selectedEndpoint.discoveryCount} storage {selectedEndpoint.discoveryCount === 1 ? 'root' : 'roots'} discovered</h4>
                  <p>Continue to review the discovered folders for this endpoint.</p>
                {:else}
                  <h4>No storage roots discovered yet</h4>
                  <p>Run a discovery to scan this endpoint and detect eligible folders.</p>
                {/if}
                <button type="button" class="sr-add-discovery-btn" disabled={Boolean(selectedEndpoint.refreshing) || loading} on:click={() => runDiscovery()}>
                  <i class={`bi ${selectedEndpoint.refreshing ? 'bi-arrow-repeat' : 'bi-broadcast-pin'}`} aria-hidden="true"></i>
                  {selectedEndpoint.refreshing ? 'Discovery running...' : `Run discovery on ${selectedEndpoint.name}`}
                </button>
              </section>
            </section>
          {:else}
            <div class="sr-add-empty-state">
              <i class="bi bi-hdd-network" aria-hidden="true"></i>
              <strong>Select an endpoint</strong>
              <span>Choose a file server from the left panel.</span>
            </div>
          {/if}
        {:else if currentStep === 2}
          <section class="sr-add-folders-step sr-add-folders-step--select">
            <div class="sr-add-folder-browser">
              <div class="sr-add-folder-browser-main">
                <div class="sr-add-step-head">
                  <div>
                    <h3>Select storage roots from {selectedEndpoint?.name ?? 'endpoint'}</h3>
                    <p>Choose one or more folders to manage as storage roots.</p>
                  </div>
                </div>

                <div class="sr-add-folder-toolbar">
                  <label class="sr-add-select-all">
                    <input
                      type="checkbox"
                      checked={eligibleFolders.length > 0 && eligibleFolders.every((folder) => effectiveSelectedFolderIds.some((folderId) => String(folderId) === String(folder.id)))}
                      disabled={eligibleFolders.length === 0}
                      on:change={selectAllEligible}
                    />
                    <span>Select all eligible</span>
                  </label>

                  <label class="sr-add-folder-search">
                    <i class="bi bi-search" aria-hidden="true"></i>
                    <input
                      type="search"
                      bind:value={folderSearch}
                      placeholder="Search path or folder name..."
                      aria-label="Search path or folder name"
                    />
                  </label>

                  <select bind:value={folderSort} aria-label="Sort discovered roots">
                    <option value="name-asc">Name A-Z</option>
                    <option value="path-asc">Path A-Z</option>
                  </select>
                </div>

                <p class="sr-add-found-count">{visibleFolders.length} {visibleFolders.length === 1 ? 'root' : 'roots'} found</p>

                {#if !selectedEndpoint}
                  <div class="sr-add-empty-state">
                    <i class="bi bi-hdd-network" aria-hidden="true"></i>
                    <strong>Select an endpoint first</strong>
                  </div>
                {:else if selectedFolders.length === 0}
                  <div class="sr-add-empty-state">
                    <i class="bi bi-folder-x" aria-hidden="true"></i>
                    <strong>No discovered folder</strong>
                    <span>Run discovery on this endpoint before importing a storage root.</span>
                  </div>
                {:else if visibleFolders.length === 0}
                  <div class="sr-add-empty-state">
                    <i class="bi bi-search" aria-hidden="true"></i>
                    <strong>No matching storage root</strong>
                    <span>Adjust your search or filters.</span>
                  </div>
                {:else}
                  <div class="sr-add-discovered-list" role="listbox" aria-label="Discovered storage roots">
                    {#each visibleFolders as folder (folder.id)}
                      {@const managed = isManagedFolder(folder)}
                      {@const tone = folderTone(folder)}
                      {@const selected = effectiveSelectedFolderIds.some((folderId) => String(folderId) === String(folder.id))}
                      <button
                        type="button"
                        class="sr-add-discovered-row"
                        class:selected
                        class:disabled={managed}
                        disabled={managed}
                        on:click={() => toggleFolder(folder)}
                      >
                        <span class="sr-add-check">
                          <input type="checkbox" checked={selected} disabled={managed} tabindex="-1" aria-hidden="true" />
                        </span>
                        <i class="bi bi-folder2-open" aria-hidden="true"></i>
                        <strong>{folder.folderName}</strong>
                        <span class="sr-add-root-path">{folder.rootPath}</span>
                        <em class={`sr-add-root-state sr-add-root-state--${tone}`}>
                          {#if tone === 'managed'}Already managed{:else if tone === 'alert'}Unreachable{:else}New{/if}
                        </em>
                      </button>
                    {/each}
                  </div>
                {/if}
              </div>

              <aside class="sr-add-selection-summary">
                <section>
                  <h4>Selection summary</h4>
                  <strong>{selectedFolderRows.length} {selectedFolderRows.length === 1 ? 'root' : 'roots'} selected</strong>
                  {#if selectedFolderRows.length > 0}
                    <ul>
                      {#each selectedFolderRows as folder (folder.id)}
                        <li>{folder.folderName}</li>
                      {/each}
                    </ul>
                  {:else}
                    <p>No storage root selected.</p>
                  {/if}
                </section>

                <section class="sr-add-default-governance">
                  <h4>Default governance</h4>
                  <dl>
                    <div>
                      <dt><i class="bi bi-person" aria-hidden="true"></i>Guardians:</dt>
                      <dd>none</dd>
                    </div>
                    <div>
                      <dt><i class="bi bi-tag" aria-hidden="true"></i>Tags:</dt>
                      <dd>none</dd>
                    </div>
                  </dl>
                </section>

                <div class="sr-add-summary-info sr-add-summary-info--strong">
                  <i class="bi bi-info-circle" aria-hidden="true"></i>
                  <span>READ and WRITE governed groups will be prepared. Effective permissions are applied on first approved access request.</span>
                </div>

                <div class="sr-add-summary-info">
                  <i class="bi bi-info-circle" aria-hidden="true"></i>
                  <span>You’ll review governance and import settings on the next step.</span>
                </div>
              </aside>
            </div>
          </section>
        {:else}
          <section class="sr-add-review-step sr-add-review-step--final">
            <div class="sr-add-review-center">
              <h3>Review import configuration</h3>

              <div class="sr-add-review-info">
                <i class="bi bi-info-circle" aria-hidden="true"></i>
                <span>{selectedFolderRows.length} storage {selectedFolderRows.length === 1 ? 'root is' : 'roots are'} ready to be imported into BornToShare.</span>
              </div>

              <section class="sr-add-review-panel sr-add-review-governance">
                <h4>Default governance</h4>
                <div class="sr-add-review-governance-row">
                  <i class="bi bi-person" aria-hidden="true"></i>
                  <span>Guardians:</span>
                  <strong>none assigned</strong>
                </div>
                <div class="sr-add-review-governance-row">
                  <i class="bi bi-tag" aria-hidden="true"></i>
                  <span>Tags:</span>
                  <strong>none</strong>
                </div>
                <p>
                  <i class="bi bi-info-circle" aria-hidden="true"></i>
                  Guardians and tags can be assigned after import from the storage root governance panel.
                </p>
              </section>

              <section class="sr-add-review-panel sr-add-access-provisioning">
                <h4>Access provisioning</h4>
                <div>
                  <input type="checkbox" checked disabled />
                  <span>READ access:</span>
                  <strong>governed group prepared</strong>
                </div>
                <div>
                  <input type="checkbox" checked disabled />
                  <span>WRITE access:</span>
                  <strong>governed group prepared</strong>
                </div>
                <div>
                  <input type="checkbox" checked disabled />
                  <span>Effective permissions:</span>
                  <strong>applied on first approved access request</strong>
                </div>
              </section>

              <section class="sr-add-review-panel sr-add-import-validation">
                <h4>Import validation</h4>
                <div>
                  <i class="bi bi-check-circle" aria-hidden="true"></i>
                  <span>{selectedFolderRows.length} new storage {selectedFolderRows.length === 1 ? 'root' : 'roots'} selected</span>
                </div>
                <div>
                  <i class="bi bi-check-circle" aria-hidden="true"></i>
                  <span>0 duplicates detected</span>
                </div>
                <div class="warning">
                  <i class="bi bi-exclamation-triangle" aria-hidden="true"></i>
                  <span>No guardians assigned yet</span>
                </div>
              </section>
            </div>

            <aside class="sr-add-import-summary">
              <h4>Import summary</h4>
              <div class="sr-add-import-summary-facts">
                <div>
                  <i class="bi bi-folder2-open" aria-hidden="true"></i>
                  <strong>{selectedFolderRows.length} storage {selectedFolderRows.length === 1 ? 'root' : 'roots'}</strong>
                </div>
                <div>
                  <i class="bi bi-hdd-network" aria-hidden="true"></i>
                  <strong>1 endpoint</strong>
                </div>
                <div>
                  <i class="bi bi-geo-alt" aria-hidden="true"></i>
                  <strong>Zone {selectedEndpoint?.zoneName ?? selectedZone?.name ?? '—'}</strong>
                </div>
              </div>

              <ul>
                <li>Import {selectedFolderRows.map((folder) => folder.folderName).join(' and ')}</li>
                <li>Prepare READ and WRITE governed groups</li>
                <li>Governance can be completed now or later</li>
              </ul>

              <div class="sr-add-import-warning">
                <i class="bi bi-exclamation-triangle" aria-hidden="true"></i>
                <span>Storage roots will be created immediately. Governed groups and effective permissions are finalized on first approved access request.</span>
              </div>
            </aside>
          </section>
        {/if}
      </main>
    </div>

    <footer class="sr-add-footer">
      <EntityActionButton compact={true} variant="secondary" label="Cancel" onClick={close} />
      {#if currentStep > 1}
        <EntityActionButton compact={true} variant="secondary" icon="bi-arrow-left" label="Back" onClick={goBack} />
      {/if}
      {#if currentStep < 3}
        <EntityActionButton
          compact={true}
          variant="primary"
          icon="bi-arrow-right"
          label="Continue"
          disabled={(currentStep === 1 && !selectedEndpoint) || (currentStep === 2 && selectedFolderRows.length === 0) || loading}
          onClick={goNext}
        />
      {:else}
        <EntityActionButton
          compact={true}
          variant="primary"
          icon={loading ? "bi-arrow-repeat" : "bi-plus-lg"}
          busy={loading}
          label={loading ? 'Creating...' : `Create ${selectedFolderRows.length} storage ${selectedFolderRows.length === 1 ? 'root' : 'roots'}`}
          disabled={selectedFolderRows.length === 0 || loading}
          onClick={create}
        />
      {/if}
    </footer>
  </div>
{/if}

<style>
  .sr-add-backdrop {
    position: fixed;
    inset: 68px 0 0;
    z-index: 1050;
    background: rgba(8, 15, 32, .66);
    backdrop-filter: blur(2px);
  }

  .sr-add-drawer {
    position: fixed;
    top: 68px;
    right: 16px;
    bottom: 16px;
    z-index: 1051;
    width: min(1120px, calc(100vw - 390px));
    min-width: min(980px, calc(100vw - 32px));
    display: grid;
    grid-template-rows: auto 1fr auto;
    overflow: hidden;
    color: #0b1d46;
    background: #fff;
    border: 1px solid #e1e7f2;
    border-radius: 10px;
    box-shadow: 0 28px 80px rgba(3, 13, 36, .36);
  }

  .sr-add-header {
    padding: 28px 34px 0;
    border-bottom: 1px solid #e6ebf4;
    background: #fff;
  }

  .sr-add-title-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
  }

  .sr-add-title-row h2 {
    margin: 0;
    color: #0b1d46;
    font-size: 29px;
    line-height: 1;
    font-weight: 700;
    letter-spacing: 0;
  }

  .sr-add-icon-btn {
    width: 36px;
    height: 36px;
    border: 0;
    border-radius: 10px;
    display: grid;
    place-items: center;
    color: #0b1d46;
    background: transparent;
    cursor: pointer;
  }

  .sr-add-icon-btn:hover {
    background: #f3f6fb;
  }

  .sr-add-stepper {
    list-style: none;
    margin: 28px 0 0;
    padding: 0 0 24px;
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 26px;
  }

  .sr-add-stepper li {
    position: relative;
    display: grid;
    grid-template-columns: 40px 1fr;
    align-items: center;
    gap: 12px;
    color: #2d4168;
  }

  .sr-add-stepper li:not(:last-child)::after {
    content: '';
    position: absolute;
    top: 20px;
    left: calc(100% + 2px);
    width: 24px;
    height: 1px;
    background: #cfd9eb;
  }

  .sr-add-stepper span {
    width: 40px;
    height: 40px;
    border: 1px solid #cdd8ec;
    border-radius: 999px;
    display: grid;
    place-items: center;
    color: #304a78;
    background: #fff;
    font-weight: 700;
  }

  .sr-add-stepper .active span,
  .sr-add-stepper .done span {
    border-color: #216be8;
    color: #fff;
    background: #216be8;
    box-shadow: 0 10px 22px rgba(33, 107, 232, .24);
  }

  .sr-add-stepper strong {
    display: block;
    font-size: 13px;
    font-weight: 700;
    color: #0d214f;
  }

  .sr-add-stepper small {
    display: block;
    margin-top: 2px;
    font-size: 12px;
    color: #52688f;
  }

  .sr-add-body {
    display: grid;
    grid-template-columns: 318px 1fr;
    min-height: 0;
  }

  .sr-add-source-panel {
    min-height: 0;
    display: grid;
    grid-template-rows: auto 1fr auto;
    border-right: 1px solid #e6ebf4;
    background: #fbfdff;
  }

  .sr-add-search {
    margin: 20px 20px 14px;
    min-height: 44px;
    display: flex;
    align-items: center;
    gap: 10px;
    border: 1px solid #d8e0ee;
    border-radius: 8px;
    padding: 0 12px;
    background: #fff;
    color: #6d7f9c;
  }

  .sr-add-search input {
    min-width: 0;
    width: 100%;
    border: 0;
    outline: 0;
    color: #253a64;
    background: transparent;
    font-size: 13px;
  }

  .sr-add-zone-list {
    min-height: 0;
    overflow: auto;
    padding: 0 20px 14px;
  }

  .sr-add-zone + .sr-add-zone {
    margin-top: 14px;
  }

  .sr-add-zone-title {
    width: 100%;
    border: 0;
    background: transparent;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 2px 0 8px;
    color: #1b315d;
    font-size: 13px;
    font-weight: 700;
    text-align: left;
    cursor: pointer;
  }

  .sr-add-zone-title .bi-caret-down-fill,
  .sr-add-zone-title .bi-caret-right-fill {
    font-size: 9px;
    color: #526a93;
  }

  .sr-add-endpoints {
    display: grid;
    gap: 10px;
    padding-left: 20px;
  }

  .sr-add-endpoint-card {
    width: 100%;
    min-height: 84px;
    border: 1px solid #dbe4f1;
    border-radius: 8px;
    display: grid;
    grid-template-columns: 22px 1fr auto;
    align-items: center;
    gap: 10px;
    padding: 13px 12px;
    text-align: left;
    color: #132958;
    background: #fff;
    box-shadow: 0 5px 16px rgba(21, 42, 84, .04);
    cursor: pointer;
    transition: border-color .14s ease, background .14s ease, box-shadow .14s ease;
  }

  .sr-add-endpoint-card:hover,
  .sr-add-endpoint-card.selected {
    border-color: #1f6bea;
    background: #f7fbff;
    box-shadow: 0 10px 22px rgba(31, 107, 234, .12);
  }

  .sr-add-endpoint-icon {
    color: #315f9f;
    font-size: 18px;
  }

  .sr-add-endpoint-main {
    min-width: 0;
    display: grid;
    gap: 3px;
  }

  .sr-add-endpoint-main strong {
    color: #0f2657;
    font-size: 14px;
    font-weight: 700;
  }

  .sr-add-endpoint-main small,
  .sr-add-endpoint-main em {
    display: flex;
    align-items: center;
    gap: 6px;
    color: #516891;
    font-size: 12px;
    font-style: normal;
    font-weight: 500;
  }

  .sr-add-chevron {
    color: #243d69;
    font-size: 13px;
  }

  .sr-add-source-footer {
    display: grid;
    gap: 12px;
    padding: 14px 20px 22px;
    border-top: 1px solid #e6ebf4;
    background: #fff;
  }

  .sr-add-refresh-all {
    min-height: 44px;
    border: 1px solid #d8e0ee;
    border-radius: 8px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    color: #152b5b;
    background: #fff;
    font-size: 13px;
    font-weight: 700;
    cursor: pointer;
  }

  .sr-add-last-refresh {
    display: flex;
    align-items: center;
    gap: 6px;
    color: #586d91;
    font-size: 12px;
  }

  .sr-add-main {
    min-height: 0;
    overflow: auto;
    padding: 28px 30px;
    background: #fff;
  }

  .sr-add-main--step2 {
    padding: 0;
    overflow: hidden;
  }

  .sr-add-main--step3 {
    padding: 0;
    overflow: hidden;
  }

  .sr-add-selected,
  .sr-add-folders-step,
  .sr-add-review-step {
    display: grid;
    gap: 26px;
  }

  .sr-add-kicker {
    margin: 0 0 14px;
    color: #1d335f;
    font-size: 13px;
    font-weight: 700;
  }

  .sr-add-selected-head,
  .sr-add-step-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 18px;
  }

  .sr-add-endpoint-title {
    display: flex;
    align-items: center;
    gap: 16px;
  }

  .sr-add-server-icon {
    width: 56px;
    height: 56px;
    border-radius: 999px;
    display: grid;
    place-items: center;
    color: #226ceb;
    background: #eef5ff;
    font-size: 24px;
  }

  .sr-add-server-icon--sm {
    width: 52px;
    height: 52px;
    font-size: 22px;
  }

  .sr-add-endpoint-title h3,
  .sr-add-step-head h3,
  .sr-add-review-step h3 {
    margin: 0;
    color: #0b1d46;
    font-size: 22px;
    font-weight: 700;
    line-height: 1.15;
  }

  .sr-add-pills {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 8px;
  }

  .sr-add-pills span {
    border: 1px solid #dbe5f4;
    border-radius: 999px;
    padding: 3px 9px;
    color: #3e557d;
    background: #f8fbff;
    font-size: 12px;
    font-weight: 600;
  }

  .sr-add-status {
    border-radius: 999px;
    padding: 6px 12px;
    font-size: 12px;
    font-weight: 700;
  }

  .sr-add-status--success {
    border: 1px solid #afe6c2;
    color: #087b37;
    background: #eafaf0;
  }

  .sr-add-status--warning {
    border: 1px solid #f5d58b;
    color: #945d00;
    background: #fff7df;
  }

  .sr-add-status--danger {
    border: 1px solid #f0b5b5;
    color: #bd1f2b;
    background: #fff0f0;
  }

  .sr-add-status--muted {
    border: 1px solid #d9e1ee;
    color: #5d6f8d;
    background: #f5f7fb;
  }

  .sr-add-metrics {
    border: 1px solid #e0e7f2;
    border-radius: 8px;
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    padding: 16px 0;
    background: #fff;
  }

  .sr-add-metrics div {
    min-width: 0;
    display: grid;
    gap: 8px;
    padding: 0 18px;
  }

  .sr-add-metrics div + div {
    border-left: 1px solid #e1e7f0;
  }

  .sr-add-metrics small,
  .sr-add-review-card small {
    color: #536990;
    font-size: 12px;
    font-weight: 500;
  }

  .sr-add-metrics strong,
  .sr-add-review-card strong {
    min-width: 0;
    display: flex;
    align-items: center;
    gap: 7px;
    color: #0d214f;
    font-size: 13px;
    font-weight: 700;
    overflow-wrap: anywhere;
  }

  .sr-add-next {
    display: grid;
    gap: 13px;
  }

  .sr-add-next h4,
  .sr-add-discovery-card h4,
  .sr-add-governance-choice h4 {
    margin: 0;
    color: #0d214f;
    font-size: 15px;
    font-weight: 700;
  }

  .sr-add-next p,
  .sr-add-discovery-card p {
    margin: 0;
    max-width: 610px;
    color: #2e4169;
    font-size: 13px;
    line-height: 1.6;
  }

  .sr-add-next ul {
    margin: 0;
    padding: 0;
    list-style: none;
    display: grid;
    gap: 12px;
  }

  .sr-add-next li {
    display: flex;
    align-items: center;
    gap: 9px;
    color: #1f345f;
    font-size: 13px;
  }

  .sr-add-next li i {
    color: #216be8;
  }

  .sr-add-discovery-card {
    min-height: 206px;
    border: 1px solid #d7e4f8;
    border-radius: 8px;
    display: grid;
    justify-items: center;
    align-content: center;
    gap: 10px;
    padding: 24px;
    text-align: center;
    background: linear-gradient(180deg, #f7fbff 0%, #edf5ff 100%);
  }

  .sr-add-discovery-card > span {
    width: 46px;
    height: 46px;
    border-radius: 999px;
    display: grid;
    place-items: center;
    color: #216be8;
    background: #e5f0ff;
    border: 1px solid #c8dcff;
    font-size: 22px;
  }

  .sr-add-discovery-btn,
  .sr-add-secondary-btn {
    min-height: 42px;
    border: 1px solid #216be8;
    border-radius: 8px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 0 18px;
    color: #fff;
    background: #216be8;
    font-size: 13px;
    font-weight: 700;
    cursor: pointer;
    box-shadow: 0 10px 24px rgba(33, 107, 232, .22);
  }

  .sr-add-secondary-btn {
    border-color: #d6dfed;
    color: #152b5b;
    background: #fff;
    box-shadow: none;
  }

  .sr-add-folder-grid {
    display: grid;
    gap: 12px;
  }

  .sr-add-endpoint-summary {
    margin: 0 20px 20px;
    border: 1px solid #dde6f2;
    border-radius: 10px;
    display: grid;
    gap: 18px;
    padding: 16px;
    background: #fff;
    box-shadow: 0 10px 24px rgba(20, 43, 86, .04);
  }

  .sr-add-review-sidebar {
    min-height: 0;
    overflow: auto;
    display: grid;
    align-content: start;
    gap: 18px;
    padding: 22px 20px;
  }

  .sr-add-review-side-card {
    border: 1px solid #dde6f2;
    border-radius: 10px;
    display: grid;
    gap: 18px;
    padding: 16px;
    background: #fff;
    box-shadow: 0 10px 24px rgba(20, 43, 86, .04);
  }

  .sr-add-review-side-card h3 {
    margin: 0;
    color: #102754;
    font-size: 16px;
    font-weight: 700;
  }

  .sr-add-review-side-card h4 {
    margin: 0;
    color: #102754;
    font-size: 17px;
    font-weight: 700;
  }

  .sr-add-sidebar-facts--review {
    padding-bottom: 0;
    border-bottom: 0;
  }

  .sr-add-review-side-card--roots {
    min-height: 332px;
    align-content: start;
  }

  .sr-add-review-side-card--roots p {
    margin: -12px 0 0;
    color: #46618b;
    font-size: 12px;
    font-weight: 600;
  }

  .sr-add-review-side-roots {
    display: grid;
    gap: 12px;
  }

  .sr-add-review-side-roots div {
    min-height: 66px;
    border: 1px solid #dfe7f2;
    border-radius: 8px;
    display: grid;
    grid-template-columns: 34px 1fr auto;
    align-items: center;
    gap: 12px;
    padding: 11px 10px;
    background: #fff;
  }

  .sr-add-review-side-roots i {
    color: #216be8;
    font-size: 24px;
  }

  .sr-add-review-side-roots span {
    min-width: 0;
    display: grid;
    gap: 4px;
  }

  .sr-add-review-side-roots strong {
    min-width: 0;
    color: #102754;
    font-size: 13px;
    font-weight: 700;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .sr-add-review-side-roots small {
    min-width: 0;
    color: #536990;
    font-size: 12px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .sr-add-review-side-roots em {
    border: 1px solid #bceacb;
    border-radius: 999px;
    padding: 4px 9px;
    color: #09803b;
    background: #ecfbf1;
    font-size: 11px;
    font-style: normal;
    font-weight: 700;
  }

  .sr-add-endpoint-summary-head {
    display: grid;
    grid-template-columns: 52px 1fr auto;
    align-items: start;
    gap: 12px;
  }

  .sr-add-endpoint-summary-head h3 {
    margin: 0;
    color: #0f2657;
    font-size: 17px;
    font-weight: 700;
  }

  .sr-add-endpoint-summary-head .sr-add-status {
    align-self: start;
    padding: 4px 10px;
    font-size: 11px;
  }

  .sr-add-sidebar-facts {
    border-top: 1px solid #edf1f7;
    border-bottom: 1px solid #edf1f7;
    display: grid;
    gap: 14px;
    padding: 16px 0;
  }

  .sr-add-sidebar-facts div {
    display: grid;
    grid-template-columns: 18px 1fr auto;
    align-items: center;
    gap: 10px;
    color: #536990;
    font-size: 12px;
  }

  .sr-add-sidebar-facts i {
    color: #4d6fa8;
  }

  .sr-add-sidebar-facts strong {
    color: #162d5a;
    font-size: 12px;
    font-weight: 700;
  }

  .sr-add-filter-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .sr-add-filter-chips button {
    min-height: 31px;
    border: 1px solid #dbe3f1;
    border-radius: 8px;
    display: inline-flex;
    align-items: center;
    gap: 7px;
    padding: 0 11px;
    color: #243a66;
    background: #fff;
    font-size: 12px;
    font-weight: 700;
    cursor: pointer;
  }

  .sr-add-filter-chips button.active {
    border-color: #93b8ff;
    color: #1a5ee5;
    background: #eff6ff;
  }

  .sr-add-filter-chips span {
    min-width: 19px;
    height: 19px;
    border-radius: 999px;
    display: grid;
    place-items: center;
    color: #1a5ee5;
    background: #eef4ff;
    font-size: 11px;
  }

  .sr-add-sidebar-note {
    margin: 0;
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 8px;
    color: #536990;
    font-size: 12px;
    line-height: 1.55;
  }

  .sr-add-sidebar-note i {
    color: #1f6bea;
    margin-top: 2px;
  }

  .sr-add-folders-step--select {
    height: 100%;
    min-height: 0;
    display: block;
  }

  .sr-add-folder-browser {
    height: 100%;
    min-height: 0;
    display: grid;
    grid-template-columns: 1fr 232px;
    gap: 26px;
    padding: 28px 26px 20px;
    overflow: hidden;
  }

  .sr-add-folder-browser-main {
    min-width: 0;
    min-height: 0;
    display: grid;
    grid-template-rows: auto auto auto 1fr;
    gap: 14px;
  }

  .sr-add-folder-browser .sr-add-step-head {
    margin-bottom: 0;
  }

  .sr-add-step-head p {
    margin: 6px 0 0;
    color: #52688f;
    font-size: 13px;
  }

  .sr-add-folder-toolbar {
    display: grid;
    grid-template-columns: 160px 1fr 160px;
    align-items: center;
    gap: 14px;
  }

  .sr-add-select-all {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    color: #213862;
    font-size: 13px;
    font-weight: 600;
  }

  .sr-add-select-all input,
  .sr-add-check input {
    width: 16px;
    height: 16px;
    accent-color: #216be8;
  }

  .sr-add-folder-search {
    min-height: 44px;
    border: 1px solid #d8e0ee;
    border-radius: 8px;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 0 13px;
    color: #6d7f9c;
    background: #fff;
  }

  .sr-add-folder-search input {
    min-width: 0;
    width: 100%;
    border: 0;
    outline: 0;
    color: #253a64;
    background: transparent;
    font-size: 13px;
  }

  .sr-add-folder-toolbar select {
    min-height: 44px;
    border: 1px solid #d8e0ee;
    border-radius: 8px;
    padding: 0 12px;
    color: #172d5a;
    background: #fff;
    font-size: 13px;
    font-weight: 600;
  }

  .sr-add-found-count {
    margin: 0;
    color: #52688f;
    font-size: 12px;
  }

  .sr-add-discovered-list {
    min-height: 0;
    overflow: auto;
    display: grid;
    align-content: start;
    gap: 8px;
    padding-right: 2px;
  }

  .sr-add-discovered-row {
    min-height: 56px;
    border: 1px solid #dde6f2;
    border-radius: 8px;
    display: grid;
    grid-template-columns: 22px 32px minmax(120px, 1fr) minmax(150px, 1.2fr) auto;
    align-items: center;
    gap: 12px;
    padding: 9px 14px;
    color: #102754;
    text-align: left;
    background: #fff;
    cursor: pointer;
  }

  .sr-add-discovered-row:hover,
  .sr-add-discovered-row.selected {
    border-color: #c9dcff;
    background: #f3f8ff;
  }

  .sr-add-discovered-row.disabled {
    cursor: not-allowed;
    opacity: .72;
    background: #fbfcfe;
  }

  .sr-add-discovered-row > .bi-folder2-open {
    color: #1f6bea;
    font-size: 22px;
  }

  .sr-add-discovered-row strong {
    min-width: 0;
    color: #102754;
    font-size: 14px;
    font-weight: 700;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .sr-add-root-path {
    min-width: 0;
    color: #4f6488;
    font-size: 12px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .sr-add-root-state {
    border-radius: 999px;
    padding: 4px 9px;
    font-size: 11px;
    font-style: normal;
    font-weight: 700;
    white-space: nowrap;
  }

  .sr-add-root-state--new {
    border: 1px solid #bceacb;
    color: #09803b;
    background: #ecfbf1;
  }

  .sr-add-root-state--managed {
    border: 1px solid #d8e0ec;
    color: #475d81;
    background: #f5f7fb;
  }

  .sr-add-root-state--alert {
    border: 1px solid #f2bd8e;
    color: #b25100;
    background: #fff4e8;
  }

  .sr-add-selection-summary {
    min-height: 0;
    border: 1px solid #dde6f2;
    border-radius: 10px;
    display: grid;
    align-content: start;
    gap: 20px;
    padding: 20px;
    background: #fff;
    box-shadow: 0 10px 24px rgba(20, 43, 86, .04);
  }

  .sr-add-selection-summary section {
    display: grid;
    gap: 12px;
  }

  .sr-add-selection-summary section + section {
    border-top: 1px solid #e5ebf4;
    padding-top: 18px;
  }

  .sr-add-selection-summary h4 {
    margin: 0;
    color: #102754;
    font-size: 14px;
    font-weight: 700;
  }

  .sr-add-selection-summary section > strong {
    color: #1f6bea;
    font-size: 13px;
    font-weight: 700;
  }

  .sr-add-selection-summary ul {
    margin: 0;
    padding-left: 18px;
    display: grid;
    gap: 8px;
    color: #152d5b;
    font-size: 13px;
    font-weight: 600;
  }

  .sr-add-selection-summary p {
    margin: 0;
    color: #667899;
    font-size: 12px;
  }

  .sr-add-default-governance dl {
    margin: 0;
    display: grid;
    gap: 14px;
  }

  .sr-add-default-governance dl div {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 10px;
  }

  .sr-add-default-governance dt {
    display: inline-flex;
    align-items: center;
    gap: 9px;
    color: #41577b;
    font-size: 13px;
    font-weight: 500;
  }

  .sr-add-default-governance dd {
    margin: 0;
    color: #52688f;
    font-size: 13px;
  }

  .sr-add-summary-info {
    border-radius: 8px;
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 8px;
    color: #3e557d;
    font-size: 12px;
    line-height: 1.45;
  }

  .sr-add-summary-info i {
    color: #216be8;
    margin-top: 2px;
  }

  .sr-add-summary-info--strong {
    border: 1px solid #d7e4f8;
    padding: 13px;
    background: #f3f8ff;
  }

  .sr-add-review-list {
    display: grid;
    gap: 10px;
  }

  .sr-add-review-step--final {
    height: 100%;
    min-height: 0;
    display: grid;
    grid-template-columns: 1fr 272px;
    gap: 26px;
    padding: 22px 26px;
    overflow: hidden;
  }

  .sr-add-review-center {
    min-height: 0;
    overflow: auto;
    display: grid;
    align-content: start;
    gap: 18px;
    padding-right: 2px;
  }

  .sr-add-review-center h3 {
    margin: 0;
    color: #102754;
    font-size: 18px;
    font-weight: 700;
  }

  .sr-add-review-info {
    min-height: 50px;
    border: 1px solid #cfe0fb;
    border-radius: 8px;
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 16px;
    color: #1b3769;
    background: #eef5ff;
    font-size: 13px;
  }

  .sr-add-review-info i {
    color: #1268ef;
    font-size: 18px;
  }

  .sr-add-review-panel {
    border: 1px solid #dde6f2;
    border-radius: 10px;
    display: grid;
    gap: 16px;
    padding: 18px;
    background: #fff;
  }

  .sr-add-review-panel h4,
  .sr-add-import-summary h4 {
    margin: 0;
    color: #102754;
    font-size: 16px;
    font-weight: 700;
  }

  .sr-add-review-governance-row {
    display: grid;
    grid-template-columns: 20px 110px 1fr 132px;
    align-items: center;
    gap: 12px;
    color: #314a73;
    font-size: 13px;
  }

  .sr-add-review-governance-row i {
    color: #1f5aa5;
    font-size: 18px;
  }

  .sr-add-review-governance-row span {
    color: #213862;
    font-weight: 600;
  }

  .sr-add-review-governance-row strong {
    color: #52688f;
    font-size: 12px;
    font-weight: 500;
  }

  .sr-add-review-governance-row button {
    min-height: 36px;
    border: 1px solid #d7dfed;
    border-radius: 7px;
    color: #11295a;
    background: #fff;
    font-size: 12px;
    font-weight: 700;
    cursor: pointer;
  }

  .sr-add-review-governance p {
    margin: 0;
    border-top: 1px solid #eef2f8;
    display: flex;
    align-items: center;
    gap: 9px;
    padding-top: 14px;
    color: #52688f;
    font-size: 12px;
  }

  .sr-add-review-governance p i {
    color: #1268ef;
  }

  .sr-add-access-provisioning div,
  .sr-add-import-validation div {
    display: grid;
    grid-template-columns: 20px minmax(142px, auto) 1fr;
    align-items: center;
    gap: 12px;
    color: #213862;
    font-size: 13px;
  }

  .sr-add-access-provisioning input {
    width: 16px;
    height: 16px;
    accent-color: #216be8;
  }

  .sr-add-access-provisioning span {
    font-weight: 600;
  }

  .sr-add-access-provisioning strong {
    color: #52688f;
    font-size: 12px;
    font-weight: 500;
  }

  .sr-add-import-validation div {
    grid-template-columns: 20px 1fr;
  }

  .sr-add-import-validation i {
    color: #12a85a;
    font-size: 18px;
  }

  .sr-add-import-validation .warning i {
    color: #f09b15;
  }

  .sr-add-import-summary {
    min-height: 0;
    border: 1px solid #dde6f2;
    border-radius: 10px;
    display: grid;
    align-content: start;
    gap: 22px;
    padding: 22px;
    background: #fff;
    box-shadow: 0 10px 24px rgba(20, 43, 86, .04);
  }

  .sr-add-import-summary-facts {
    border-bottom: 1px solid #e6edf5;
    display: grid;
    gap: 18px;
    padding-bottom: 20px;
  }

  .sr-add-import-summary-facts div {
    display: grid;
    grid-template-columns: 28px 1fr;
    align-items: center;
    gap: 12px;
  }

  .sr-add-import-summary-facts i {
    color: #244675;
    font-size: 24px;
  }

  .sr-add-import-summary-facts strong {
    color: #152d5b;
    font-size: 14px;
    font-weight: 700;
  }

  .sr-add-import-summary ul {
    margin: 0;
    padding-left: 18px;
    display: grid;
    gap: 18px;
    color: #132958;
    font-size: 14px;
    line-height: 1.55;
  }

  .sr-add-import-warning {
    border: 1px solid #f1cf88;
    border-radius: 8px;
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 12px;
    padding: 16px;
    color: #1d3158;
    background: #fff8e8;
    font-size: 13px;
    line-height: 1.6;
  }

  .sr-add-import-warning i {
    color: #f09b15;
    font-size: 20px;
    margin-top: 2px;
  }

  .sr-add-folder-card {
    min-height: 72px;
    border: 1px solid #dfe7f2;
    border-radius: 10px;
    display: grid;
    grid-template-columns: 34px 1fr auto;
    align-items: center;
    gap: 12px;
    padding: 12px 14px;
    text-align: left;
    background: #fff;
    color: #122858;
    cursor: pointer;
  }

  .sr-add-folder-card:hover,
  .sr-add-folder-card.selected {
    border-color: #216be8;
    background: #f7fbff;
  }

  .sr-add-folder-card > i:first-child {
    color: #216be8;
    font-size: 22px;
  }

  .sr-add-folder-card span {
    min-width: 0;
    display: grid;
    gap: 4px;
  }

  .sr-add-folder-card strong {
    font-size: 14px;
    font-weight: 700;
  }

  .sr-add-folder-card small {
    color: #5b7095;
    font-size: 12px;
    overflow-wrap: anywhere;
  }

  .sr-add-selected-mark {
    color: #216be8;
  }

  .sr-add-review-card {
    border: 1px solid #dfe7f2;
    border-radius: 10px;
    display: grid;
    gap: 16px;
    padding: 18px;
    background: #fbfdff;
  }

  .sr-add-review-card div {
    display: grid;
    gap: 6px;
  }

  .sr-add-governance-choice {
    display: grid;
    gap: 12px;
  }

  .sr-add-governance-choice label {
    border: 1px solid #dfe7f2;
    border-radius: 10px;
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 12px;
    padding: 14px;
    cursor: pointer;
    background: #fff;
  }

  .sr-add-governance-choice label.active {
    border-color: #216be8;
    background: #f7fbff;
  }

  .sr-add-governance-choice input {
    margin-top: 4px;
  }

  .sr-add-governance-choice span {
    display: grid;
    gap: 4px;
  }

  .sr-add-governance-choice strong {
    color: #102754;
    font-size: 14px;
    font-weight: 700;
  }

  .sr-add-governance-choice small {
    color: #566d91;
    font-size: 12px;
    line-height: 1.45;
  }

  .sr-add-empty-state,
  .sr-add-empty-compact {
    border: 1px dashed #ced8ea;
    border-radius: 12px;
    display: grid;
    justify-items: center;
    align-content: center;
    gap: 8px;
    padding: 32px;
    color: #536a91;
    text-align: center;
    background: #f8fbff;
  }

  .sr-add-empty-state {
    min-height: 320px;
  }

  .sr-add-empty-state i {
    color: #8aa0c2;
    font-size: 34px;
  }

  .sr-add-empty-state strong {
    color: #213862;
    font-size: 16px;
  }

  .sr-add-empty-state span,
  .sr-add-empty-compact {
    font-size: 13px;
  }

  .sr-add-footer {
    min-height: 74px;
    border-top: 1px solid #e6ebf4;
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 12px;
    padding: 16px 30px;
    background: #fff;
  }

  .sr-add-discovery-btn:disabled,
  .sr-add-secondary-btn:disabled,
  .sr-add-refresh-all:disabled {
    cursor: not-allowed;
    opacity: .55;
    box-shadow: none;
  }

  .sr-add-dot {
    width: 7px;
    height: 7px;
    border-radius: 999px;
    display: inline-block;
    flex: 0 0 auto;
    background: #98a7bf;
  }

  .sr-add-dot--success {
    background: #22ae60;
  }

  .sr-add-dot--warning {
    background: #e3a11d;
  }

  .sr-add-dot--danger {
    background: #db3947;
  }

  .sr-add-dot--muted {
    background: #98a7bf;
  }

  @media (max-width: 1180px) {
    .sr-add-drawer {
      left: 16px;
      width: auto;
      min-width: 0;
    }
  }

  @media (max-width: 760px) {
    .sr-add-backdrop {
      inset: 0;
    }

    .sr-add-drawer {
      inset: 10px;
      width: auto;
      min-width: 0;
    }

    .sr-add-body {
      grid-template-columns: 1fr;
      overflow: auto;
    }

    .sr-add-source-panel {
      min-height: 360px;
      border-right: 0;
      border-bottom: 1px solid #e6ebf4;
    }

    .sr-add-main {
      overflow: visible;
    }

    .sr-add-stepper {
      grid-template-columns: 1fr;
      gap: 12px;
    }

    .sr-add-stepper li:not(:last-child)::after {
      display: none;
    }

    .sr-add-metrics {
      grid-template-columns: 1fr;
    }

    .sr-add-metrics div + div {
      border-left: 0;
      border-top: 1px solid #e1e7f0;
      padding-top: 14px;
    }
  }
</style>
