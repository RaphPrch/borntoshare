<script lang="ts">
  import { rootPathKey } from '$lib/utils/storage-roots';
  import { formatDateTime } from '$lib/utils/format';
  const ENDPOINT_STATE_VARIANTS = { success: 'success', warning: 'info', danger: 'error', muted: 'muted' } as const;
  import StatusBadge from '$lib/components/ui/StatusBadge.svelte';
  import { t } from '$lib/i18n';
  import WizardShell from '$lib/components/ui/WizardShell.svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import { createEventDispatcher } from 'svelte';
  import EntityActionButton from '$lib/components/entity/EntityActionButton.svelte';
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
    return formatDateTime(iso);
  };

  const normalized = (value: unknown) => String(value ?? '').trim().toLowerCase();
  const pathKey = (endpointId: unknown, rootPath: unknown) => `${Number(endpointId ?? 0)}:${rootPathKey(rootPath)}`;

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
    if (raw === 'disabled' || raw === 'inactive') return { label: t('Disabled'), tone: 'muted' };
    if (raw.includes('fail') || raw.includes('unreach') || raw.includes('error')) return { label: t('Unreachable'), tone: 'danger' };
    if (raw === 'running') return { label: t('Running'), tone: 'warning' };
    if (raw.includes('success') || raw.includes('ok') || raw.includes('reach') || raw.includes('healthy')) {
      return { label: t('Reachable'), tone: 'success' };
    }
    if (endpoint?.refreshStatus === 'success' || endpoint?.discoveryCount > 0) return { label: t('Reachable'), tone: 'success' };
    return { label: t('Unknown'), tone: 'muted' };
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

<WizardShell
  {open}
  onClose={close}
  flush
  title={t('Add storage roots')}
  subtitle={t('Discover folders on a storage endpoint and govern them as storage roots.')}
  iconClass="bi bi-folder-plus"
  ariaLabelledby="sr-add-title"
  current={currentStep}
  steps={[
    { label: t('Select source'), hint: t('Choose zone and endpoint') },
    { label: t('Select storage roots'), hint: t('Discover and select folders') },
    { label: t('Review & import'), hint: t('Set governance and confirm') }
  ]}
>
    <div class="sr-add-body">
      <aside class="sr-add-source-panel">
        {#if currentStep === 1}
          <label class="sr-add-search">
            <i class="bi bi-search" aria-hidden="true"></i>
            <input
              type="search"
              bind:value={search}
              placeholder={t('Search zones or endpoints...')}
              aria-label={t('Search zones or endpoints')}
            />
          </label>

          <div class="sr-add-zone-list">
            {#if filteredZones().length === 0}
              <div class="sr-add-empty-compact">{t('No source matches your search.')}</div>
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
                            <em>{t('{discoveryCount} {value} discovered', { discoveryCount: endpoint.discoveryCount, value: (endpoint.discoveryCount === 1 ? 'root' : 'roots') })}</em>
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
              {t('Refresh all endpoints')}
            </button>
            <div class="sr-add-last-refresh">
              <span class="sr-add-dot sr-add-dot--success"></span>
              {t('Last refresh: {fmt}', { fmt: fmt(lastRefreshAt) })}
            </div>
          </footer>
        {:else if currentStep === 2}
          {@const state = endpointState(selectedEndpoint)}
          <label class="sr-add-search">
            <i class="bi bi-search" aria-hidden="true"></i>
            <input
              type="search"
              bind:value={folderSearch}
              placeholder={t('Search discovered roots...')}
              aria-label={t('Search discovered roots')}
            />
          </label>

          <div class="sr-add-endpoint-summary">
            <div class="sr-add-endpoint-summary-head">
              <span class="sr-add-server-icon sr-add-server-icon--sm"><i class="bi bi-hdd-network" aria-hidden="true"></i></span>
              <div>
                <h3>{selectedEndpoint?.name ?? t('Endpoint')}</h3>
                <div class="sr-add-pills">
                  <span>{t('Zone {value}', { value: (selectedEndpoint?.zoneName ?? selectedZone?.name ?? '—') })}</span>
                  <span>{selectedEndpoint?.protocol ?? '—'}</span>
                </div>
              </div>
              <StatusBadge compact variant={ENDPOINT_STATE_VARIANTS[state.tone]} label={state.label} />
            </div>

            <div class="sr-add-sidebar-facts">
              <div>
                <i class="bi bi-clock" aria-hidden="true"></i>
                <span>{t('Last discovery')}</span>
                <strong>{fmt(selectedEndpoint?.lastRefreshAt ?? selectedEndpoint?.lastProbeAt)}</strong>
              </div>
              <div>
                <i class="bi bi-folder2-open" aria-hidden="true"></i>
                <span>{t('{value} discovered roots', { value: (selectedEndpoint?.discoveryCount ?? 0) })}</span>
              </div>
            </div>

            <div class="sr-add-filter-chips" aria-label={t('Discovery filters')}>
              <button type="button" class:active={folderFilter === 'all'} on:click={() => (folderFilter = 'all')}>{t('All')} <span>{folderCounts.all}</span></button>
              <button type="button" class:active={folderFilter === 'new'} on:click={() => (folderFilter = 'new')}>{t('New')} <span>{folderCounts.new}</span></button>
              <button type="button" class:active={folderFilter === 'managed'} on:click={() => (folderFilter = 'managed')}>{t('Already managed')} <span>{folderCounts.managed}</span></button>
              <button type="button" class:active={folderFilter === 'alerts'} on:click={() => (folderFilter = 'alerts')}>{t('Alerts')} <span>{folderCounts.alerts}</span></button>
            </div>

            <button type="button" class="sr-add-refresh-all" disabled={Boolean(selectedEndpoint?.refreshing) || loading} on:click={() => runDiscovery()}>
              <i class="bi bi-arrow-clockwise" aria-hidden="true"></i>
              {t('Run discovery again')}
            </button>

            <p class="sr-add-sidebar-note">
              <i class="bi bi-info-circle" aria-hidden="true"></i>
              {t('Folders that are already managed cannot be selected again.')}
            </p>
          </div>
        {:else}
          {@const state = endpointState(selectedEndpoint)}
          <div class="sr-add-review-sidebar">
            <section class="sr-add-review-side-card">
              <h3>{t('Selected endpoint')}</h3>
              <div class="sr-add-endpoint-summary-head">
                <span class="sr-add-server-icon sr-add-server-icon--sm"><i class="bi bi-hdd-network" aria-hidden="true"></i></span>
                <div>
                  <h4>{selectedEndpoint?.name ?? t('Endpoint')}</h4>
                  <div class="sr-add-pills">
                    <span>{t('Zone {value}', { value: (selectedEndpoint?.zoneName ?? selectedZone?.name ?? '—') })}</span>
                    <span>{selectedEndpoint?.protocol ?? '—'}</span>
                  </div>
                </div>
                <StatusBadge compact variant={ENDPOINT_STATE_VARIANTS[state.tone]} label={state.label} />
              </div>

              <div class="sr-add-sidebar-facts sr-add-sidebar-facts--review">
                <div>
                  <i class="bi bi-clock" aria-hidden="true"></i>
                  <span>{t('Last discovery')}</span>
                  <strong>{fmt(selectedEndpoint?.lastRefreshAt ?? selectedEndpoint?.lastProbeAt)}</strong>
                </div>
                <div>
                  <i class="bi bi-folder2" aria-hidden="true"></i>
                  <span>{t('Base path')}</span>
                  <strong>{selectedEndpoint?.basePath || '—'}</strong>
                </div>
                <div>
                  <i class="bi bi-folder2-open" aria-hidden="true"></i>
                  <span>{t('Discovered roots')}</span>
                  <strong>{selectedEndpoint?.discoveryCount ?? 0}</strong>
                </div>
              </div>
            </section>

            <section class="sr-add-review-side-card sr-add-review-side-card--roots">
              <h3>{t('Selected storage roots')}</h3>
              <p>{t('{selectedFolderRowsCount} selected', { selectedFolderRowsCount: selectedFolderRows.length })}</p>
              <div class="sr-add-review-side-roots">
                {#each selectedFolderRows as folder (folder.id)}
                  <div>
                    <i class="bi bi-folder2-open" aria-hidden="true"></i>
                    <span>
                      <strong>{folder.folderName}</strong>
                      <small>{folder.rootPath}</small>
                    </span>
                    <em>{t('New')}</em>
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
                  <p class="sr-add-kicker">{t('Selected endpoint')}</p>
                  <div class="sr-add-endpoint-title">
                    <span class="sr-add-server-icon"><i class="bi bi-hdd-network" aria-hidden="true"></i></span>
                    <div>
                      <h3>{selectedEndpoint.name}</h3>
                      <div class="sr-add-pills">
                        <span>{t('Zone {value}', { value: (selectedEndpoint.zoneName ?? selectedZone?.name ?? '—') })}</span>
                        <span>{t('Protocol {value}', { value: (selectedEndpoint.protocol ?? '—') })}</span>
                      </div>
                    </div>
                  </div>
                </div>
                <StatusBadge compact variant={ENDPOINT_STATE_VARIANTS[state.tone]} label={state.label} />
              </div>

              <div class="sr-add-metrics" aria-label={t('Endpoint summary')}>
                <div>
                  <small>{t('Last discovery')}</small>
                  <strong>{fmt(selectedEndpoint.lastRefreshAt ?? selectedEndpoint.lastProbeAt)}</strong>
                </div>
                <div>
                  <small>{t('Base path')}</small>
                  <strong>{selectedEndpoint.basePath || '—'}</strong>
                </div>
                <div>
                  <small>{t('Discovered roots')}</small>
                  <strong>{selectedEndpoint.discoveryCount}</strong>
                </div>
                <div>
                  <small>{t('Status')}</small>
                  <strong><span class={statusDotClass(selectedEndpoint)}></span>{state.label}</strong>
                </div>
              </div>

              <section class="sr-add-next">
                <h4>{t('What happens next?')}</h4>
                <p>{t('We will scan the configured base paths on this endpoint and list eligible folders that can be managed as storage roots.')}</p>
                <ul>
                  <li><i class="bi bi-check-circle-fill" aria-hidden="true"></i>{t('You will be able to review and select folders.')}</li>
                  <li><i class="bi bi-check-circle-fill" aria-hidden="true"></i>{t('No storage root will be created until you confirm.')}</li>
                </ul>
              </section>

              <section class="sr-add-discovery-card">
                <span><i class="bi bi-info-circle" aria-hidden="true"></i></span>
                {#if selectedEndpoint.discoveryCount > 0}
                  <h4>{t('{discoveryCount} storage {value} discovered', { discoveryCount: selectedEndpoint.discoveryCount, value: (selectedEndpoint.discoveryCount === 1 ? 'root' : 'roots') })}</h4>
                  <p>{t('Continue to review the discovered folders for this endpoint.')}</p>
                {:else}
                  <h4>{t('No storage roots discovered yet')}</h4>
                  <p>{t('Run a discovery to scan this endpoint and detect eligible folders.')}</p>
                {/if}
                <button type="button" class="sr-add-discovery-btn" disabled={Boolean(selectedEndpoint.refreshing) || loading} on:click={() => runDiscovery()}>
                  <i class={`bi ${selectedEndpoint.refreshing ? 'bi-arrow-repeat' : 'bi-broadcast-pin'}`} aria-hidden="true"></i>
                  {selectedEndpoint.refreshing ? t('Discovery running...') : t('Run discovery on {name}', { name: selectedEndpoint.name })}
                </button>
              </section>
            </section>
          {:else}
            <div class="sr-add-empty-state">
              <i class="bi bi-hdd-network" aria-hidden="true"></i>
              <strong>{t('Select an endpoint')}</strong>
              <span>{t('Choose a file server from the left panel.')}</span>
            </div>
          {/if}
        {:else if currentStep === 2}
          <section class="sr-add-folders-step sr-add-folders-step--select">
            <div class="sr-add-folder-browser">
              <div class="sr-add-folder-browser-main">
                <div class="sr-add-step-head">
                  <div>
                    <h3>{t('Select storage roots from {value}', { value: (selectedEndpoint?.name ?? 'endpoint') })}</h3>
                    <p>{t('Choose one or more folders to manage as storage roots.')}</p>
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
                    <span>{t('Select all eligible')}</span>
                  </label>

                  <label class="sr-add-folder-search">
                    <i class="bi bi-search" aria-hidden="true"></i>
                    <input
                      type="search"
                      bind:value={folderSearch}
                      placeholder={t('Search path or folder name...')}
                      aria-label={t('Search path or folder name')}
                    />
                  </label>

                  <select bind:value={folderSort} aria-label={t('Sort discovered roots')}>
                    <option value="name-asc">{t('Name A-Z')}</option>
                    <option value="path-asc">{t('Path A-Z')}</option>
                  </select>
                </div>

                <p class="sr-add-found-count">{t('{visibleFoldersCount} {value} found', { visibleFoldersCount: visibleFolders.length, value: (visibleFolders.length === 1 ? 'root' : 'roots') })}</p>

                {#if !selectedEndpoint}
                  <div class="sr-add-empty-state">
                    <i class="bi bi-hdd-network" aria-hidden="true"></i>
                    <strong>{t('Select an endpoint first')}</strong>
                  </div>
                {:else if selectedFolders.length === 0}
                  <div class="sr-add-empty-state">
                    <i class="bi bi-folder-x" aria-hidden="true"></i>
                    <strong>{t('No discovered folder')}</strong>
                    <span>{t('Run discovery on this endpoint before importing a storage root.')}</span>
                  </div>
                {:else if visibleFolders.length === 0}
                  <div class="sr-add-empty-state">
                    <i class="bi bi-search" aria-hidden="true"></i>
                    <strong>{t('No matching storage root')}</strong>
                    <span>{t('Adjust your search or filters.')}</span>
                  </div>
                {:else}
                  <div class="sr-add-discovered-list" role="listbox" aria-label={t('Discovered storage roots')}>
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
                          {#if tone === 'managed'}{t('Already managed')}{:else if tone === 'alert'}{t('Unreachable')}{:else}{t('New')}{/if}
                        </em>
                      </button>
                    {/each}
                  </div>
                {/if}
              </div>

              <aside class="sr-add-selection-summary">
                <section>
                  <h4>{t('Selection summary')}</h4>
                  <strong>{t('{selectedFolderRowsCount} {value} selected', { selectedFolderRowsCount: selectedFolderRows.length, value: (selectedFolderRows.length === 1 ? 'root' : 'roots') })}</strong>
                  {#if selectedFolderRows.length > 0}
                    <ul>
                      {#each selectedFolderRows as folder (folder.id)}
                        <li>{folder.folderName}</li>
                      {/each}
                    </ul>
                  {:else}
                    <p>{t('No storage root selected.')}</p>
                  {/if}
                </section>

                <section class="sr-add-default-governance">
                  <h4>{t('Default governance')}</h4>
                  <dl>
                    <div>
                      <dt><i class="bi bi-person" aria-hidden="true"></i>{t('Guardians:')}</dt>
                      <dd>none</dd>
                    </div>
                    <div>
                      <dt><i class="bi bi-tag" aria-hidden="true"></i>{t('Tags:')}</dt>
                      <dd>none</dd>
                    </div>
                  </dl>
                </section>

                <div class="sr-add-summary-info sr-add-summary-info--strong">
                  <i class="bi bi-info-circle" aria-hidden="true"></i>
                  <span>{t('READ and WRITE governed groups will be prepared. Effective permissions are applied on first approved access request.')}</span>
                </div>

                <div class="sr-add-summary-info">
                  <i class="bi bi-info-circle" aria-hidden="true"></i>
                  <span>{t('You’ll review governance and import settings on the next step.')}</span>
                </div>
              </aside>
            </div>
          </section>
        {:else}
          <section class="sr-add-review-step sr-add-review-step--final">
            <div class="sr-add-review-center">
              <h3>{t('Review import configuration')}</h3>

              <div class="sr-add-review-info">
                <i class="bi bi-info-circle" aria-hidden="true"></i>
                <span>{t('{selectedFolderRowsCount} storage {value} ready to be imported into BornToShare.', { selectedFolderRowsCount: selectedFolderRows.length, value: (selectedFolderRows.length === 1 ? 'root is' : 'roots are') })}</span>
              </div>

              <section class="sr-add-review-panel sr-add-review-governance">
                <h4>{t('Default governance')}</h4>
                <div class="sr-add-review-governance-row">
                  <i class="bi bi-person" aria-hidden="true"></i>
                  <span>{t('Guardians:')}</span>
                  <strong>{t('none assigned')}</strong>
                </div>
                <div class="sr-add-review-governance-row">
                  <i class="bi bi-tag" aria-hidden="true"></i>
                  <span>{t('Tags:')}</span>
                  <strong>none</strong>
                </div>
                <p>
                  <i class="bi bi-info-circle" aria-hidden="true"></i>
                  {t('Guardians and tags can be assigned after import from the storage root governance panel.')}
                </p>
              </section>

              <section class="sr-add-review-panel sr-add-access-provisioning">
                <h4>{t('Access provisioning')}</h4>
                <div>
                  <input type="checkbox" checked disabled />
                  <span>{t('READ access:')}</span>
                  <strong>{t('governed group prepared')}</strong>
                </div>
                <div>
                  <input type="checkbox" checked disabled />
                  <span>{t('WRITE access:')}</span>
                  <strong>{t('governed group prepared')}</strong>
                </div>
                <div>
                  <input type="checkbox" checked disabled />
                  <span>{t('Effective permissions:')}</span>
                  <strong>{t('applied on first approved access request')}</strong>
                </div>
              </section>

              <section class="sr-add-review-panel sr-add-import-validation">
                <h4>{t('Import validation')}</h4>
                <div>
                  <i class="bi bi-check-circle" aria-hidden="true"></i>
                  <span>{t('{selectedFolderRowsCount} new storage {value} selected', { selectedFolderRowsCount: selectedFolderRows.length, value: (selectedFolderRows.length === 1 ? 'root' : 'roots') })}</span>
                </div>
                <div>
                  <i class="bi bi-check-circle" aria-hidden="true"></i>
                  <span>{t('0 duplicates detected')}</span>
                </div>
                <div class="warning">
                  <i class="bi bi-exclamation-triangle" aria-hidden="true"></i>
                  <span>{t('No guardians assigned yet')}</span>
                </div>
              </section>
            </div>

            <aside class="sr-add-import-summary">
              <h4>{t('Import summary')}</h4>
              <div class="sr-add-import-summary-facts">
                <div>
                  <i class="bi bi-folder2-open" aria-hidden="true"></i>
                  <strong>{t('{selectedFolderRowsCount} storage {value}', { selectedFolderRowsCount: selectedFolderRows.length, value: (selectedFolderRows.length === 1 ? 'root' : 'roots') })}</strong>
                </div>
                <div>
                  <i class="bi bi-hdd-network" aria-hidden="true"></i>
                  <strong>{t('1 endpoint')}</strong>
                </div>
                <div>
                  <i class="bi bi-geo-alt" aria-hidden="true"></i>
                  <strong>{t('Zone {value}', { value: (selectedEndpoint?.zoneName ?? selectedZone?.name ?? '—') })}</strong>
                </div>
              </div>

              <ul>
                <li>{t('Import {value}', { value: (selectedFolderRows.map((folder) => folder.folderName).join(' and ')) })}</li>
                <li>{t('Prepare READ and WRITE governed groups')}</li>
                <li>{t('Governance can be completed now or later')}</li>
              </ul>

              <InlineAlert tone="warning" compact>
                {t('Storage roots will be created immediately. Governed groups and effective permissions are finalized on first approved access request.')}
              </InlineAlert>
            </aside>
          </section>
        {/if}
      </main>
    </div>

  <svelte:fragment slot="footer">
    <button type="button" class="b2s-btn b2s-btn-ghost" on:click={close}>{t('Cancel')}</button>
    {#if currentStep > 1}
      <button type="button" class="b2s-btn b2s-btn-secondary" on:click={goBack}>
        <i class="bi bi-arrow-left" aria-hidden="true"></i>
        {t('Back')}
      </button>
    {/if}
    {#if currentStep < 3}
      <button
        type="button"
        class="b2s-btn b2s-btn-primary"
        disabled={(currentStep === 1 && !selectedEndpoint) || (currentStep === 2 && selectedFolderRows.length === 0) || loading}
        on:click={goNext}
      >
        {t('Continue')}
      </button>
    {:else}
      <button type="button" class="b2s-btn b2s-btn-primary" disabled={selectedFolderRows.length === 0 || loading} on:click={create}>
        {#if loading}
          {t('Creating...')}
        {:else if selectedFolderRows.length === 1}
          {t('Create 1 storage root')}
        {:else}
          {t('Create {count} storage roots', { count: selectedFolderRows.length })}
        {/if}
      </button>
    {/if}
  </svelte:fragment>
</WizardShell>

<style>

  .sr-add-body {
    flex: 1 1 auto;
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
    border-radius: var(--b2s-radius-sm);
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
    font-size: var(--b2s-fs-sm);
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
    font-size: var(--b2s-fs-sm);
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
    border-radius: var(--b2s-radius-sm);
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
    font-size: var(--b2s-fs-md);
    font-weight: 700;
  }

  .sr-add-endpoint-main small,
  .sr-add-endpoint-main em {
    display: flex;
    align-items: center;
    gap: 6px;
    color: #516891;
    font-size: var(--b2s-fs-xs);
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
    border-radius: var(--b2s-radius-sm);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    color: #152b5b;
    background: #fff;
    font-size: var(--b2s-fs-sm);
    font-weight: 700;
    cursor: pointer;
  }

  .sr-add-last-refresh {
    display: flex;
    align-items: center;
    gap: 6px;
    color: #586d91;
    font-size: var(--b2s-fs-xs);
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
    font-size: var(--b2s-fs-sm);
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
    border-radius: var(--b2s-radius-pill);
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
    font-size: var(--b2s-fs-2xl);
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
    border-radius: var(--b2s-radius-pill);
    padding: 3px 9px;
    color: #3e557d;
    background: #f8fbff;
    font-size: var(--b2s-fs-xs);
    font-weight: 600;
  }

  .sr-add-metrics {
    border: 1px solid #e0e7f2;
    border-radius: var(--b2s-radius-sm);
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

  .sr-add-metrics small {
    color: #536990;
    font-size: var(--b2s-fs-xs);
    font-weight: 500;
  }

  .sr-add-metrics strong {
    min-width: 0;
    display: flex;
    align-items: center;
    gap: 7px;
    color: #0d214f;
    font-size: var(--b2s-fs-sm);
    font-weight: 700;
    overflow-wrap: anywhere;
  }

  .sr-add-next {
    display: grid;
    gap: 13px;
  }

  .sr-add-next h4,
  .sr-add-discovery-card h4 {
    margin: 0;
    color: #0d214f;
    font-size: var(--b2s-fs-lg);
    font-weight: 700;
  }

  .sr-add-next p,
  .sr-add-discovery-card p {
    margin: 0;
    max-width: 610px;
    color: #2e4169;
    font-size: var(--b2s-fs-sm);
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
    font-size: var(--b2s-fs-sm);
  }

  .sr-add-next li i {
    color: #216be8;
  }

  .sr-add-discovery-card {
    min-height: 206px;
    border: 1px solid #d7e4f8;
    border-radius: var(--b2s-radius-sm);
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
    border-radius: var(--b2s-radius-pill);
    display: grid;
    place-items: center;
    color: #216be8;
    background: #e5f0ff;
    border: 1px solid #c8dcff;
    font-size: var(--b2s-fs-2xl);
  }

  .sr-add-discovery-btn {
    min-height: 42px;
    border: 1px solid #216be8;
    border-radius: var(--b2s-radius-sm);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 0 18px;
    color: #fff;
    background: #216be8;
    font-size: var(--b2s-fs-sm);
    font-weight: 700;
    cursor: pointer;
    box-shadow: 0 10px 24px rgba(33, 107, 232, .22);
  }

  .sr-add-endpoint-summary {
    margin: 0 20px 20px;
    border: 1px solid #dde6f2;
    border-radius: var(--b2s-radius-md);
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
    border-radius: var(--b2s-radius-md);
    display: grid;
    gap: 18px;
    padding: 16px;
    background: #fff;
    box-shadow: 0 10px 24px rgba(20, 43, 86, .04);
  }

  .sr-add-review-side-card h3 {
    margin: 0;
    color: #102754;
    font-size: var(--b2s-fs-lg);
    font-weight: 700;
  }

  .sr-add-review-side-card h4 {
    margin: 0;
    color: #102754;
    font-size: var(--b2s-fs-lg);
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
    font-size: var(--b2s-fs-xs);
    font-weight: 600;
  }

  .sr-add-review-side-roots {
    display: grid;
    gap: 12px;
  }

  .sr-add-review-side-roots div {
    min-height: 66px;
    border: 1px solid #dfe7f2;
    border-radius: var(--b2s-radius-sm);
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
    font-size: var(--b2s-fs-sm);
    font-weight: 700;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .sr-add-review-side-roots small {
    min-width: 0;
    color: #536990;
    font-size: var(--b2s-fs-xs);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .sr-add-review-side-roots em {
    border: 1px solid #bceacb;
    border-radius: var(--b2s-radius-pill);
    padding: 4px 9px;
    color: #09803b;
    background: #ecfbf1;
    font-size: var(--b2s-fs-xs);
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
    font-size: var(--b2s-fs-lg);
    font-weight: 700;
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
    font-size: var(--b2s-fs-xs);
  }

  .sr-add-sidebar-facts i {
    color: #4d6fa8;
  }

  .sr-add-sidebar-facts strong {
    color: #162d5a;
    font-size: var(--b2s-fs-xs);
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
    border-radius: var(--b2s-radius-sm);
    display: inline-flex;
    align-items: center;
    gap: 7px;
    padding: 0 11px;
    color: #243a66;
    background: #fff;
    font-size: var(--b2s-fs-xs);
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
    border-radius: var(--b2s-radius-pill);
    display: grid;
    place-items: center;
    color: #1a5ee5;
    background: #eef4ff;
    font-size: var(--b2s-fs-xs);
  }

  .sr-add-sidebar-note {
    margin: 0;
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 8px;
    color: #536990;
    font-size: var(--b2s-fs-xs);
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
    font-size: var(--b2s-fs-sm);
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
    font-size: var(--b2s-fs-sm);
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
    border-radius: var(--b2s-radius-sm);
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
    font-size: var(--b2s-fs-sm);
  }

  .sr-add-folder-toolbar select {
    min-height: 44px;
    border: 1px solid #d8e0ee;
    border-radius: var(--b2s-radius-sm);
    padding: 0 12px;
    color: #172d5a;
    background: #fff;
    font-size: var(--b2s-fs-sm);
    font-weight: 600;
  }

  .sr-add-found-count {
    margin: 0;
    color: #52688f;
    font-size: var(--b2s-fs-xs);
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
    border-radius: var(--b2s-radius-sm);
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
    font-size: var(--b2s-fs-md);
    font-weight: 700;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .sr-add-root-path {
    min-width: 0;
    color: #4f6488;
    font-size: var(--b2s-fs-xs);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .sr-add-root-state {
    border-radius: var(--b2s-radius-pill);
    padding: 4px 9px;
    font-size: var(--b2s-fs-xs);
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
    border-radius: var(--b2s-radius-md);
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
    font-size: var(--b2s-fs-md);
    font-weight: 700;
  }

  .sr-add-selection-summary section > strong {
    color: #1f6bea;
    font-size: var(--b2s-fs-sm);
    font-weight: 700;
  }

  .sr-add-selection-summary ul {
    margin: 0;
    padding-left: 18px;
    display: grid;
    gap: 8px;
    color: #152d5b;
    font-size: var(--b2s-fs-sm);
    font-weight: 600;
  }

  .sr-add-selection-summary p {
    margin: 0;
    color: #667899;
    font-size: var(--b2s-fs-xs);
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
    font-size: var(--b2s-fs-sm);
    font-weight: 500;
  }

  .sr-add-default-governance dd {
    margin: 0;
    color: #52688f;
    font-size: var(--b2s-fs-sm);
  }

  .sr-add-summary-info {
    border-radius: var(--b2s-radius-sm);
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 8px;
    color: #3e557d;
    font-size: var(--b2s-fs-xs);
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
    font-size: var(--b2s-fs-xl);
    font-weight: 700;
  }

  .sr-add-review-info {
    min-height: 50px;
    border: 1px solid #cfe0fb;
    border-radius: var(--b2s-radius-sm);
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 16px;
    color: #1b3769;
    background: #eef5ff;
    font-size: var(--b2s-fs-sm);
  }

  .sr-add-review-info i {
    color: #1268ef;
    font-size: 18px;
  }

  .sr-add-review-panel {
    border: 1px solid #dde6f2;
    border-radius: var(--b2s-radius-md);
    display: grid;
    gap: 16px;
    padding: 18px;
    background: #fff;
  }

  .sr-add-review-panel h4,
  .sr-add-import-summary h4 {
    margin: 0;
    color: #102754;
    font-size: var(--b2s-fs-lg);
    font-weight: 700;
  }

  .sr-add-review-governance-row {
    display: grid;
    grid-template-columns: 20px 110px 1fr 132px;
    align-items: center;
    gap: 12px;
    color: #314a73;
    font-size: var(--b2s-fs-sm);
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
    font-size: var(--b2s-fs-xs);
    font-weight: 500;
  }

  .sr-add-review-governance p {
    margin: 0;
    border-top: 1px solid #eef2f8;
    display: flex;
    align-items: center;
    gap: 9px;
    padding-top: 14px;
    color: #52688f;
    font-size: var(--b2s-fs-xs);
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
    font-size: var(--b2s-fs-sm);
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
    font-size: var(--b2s-fs-xs);
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
    border-radius: var(--b2s-radius-md);
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
    font-size: var(--b2s-fs-md);
    font-weight: 700;
  }

  .sr-add-import-summary ul {
    margin: 0;
    padding-left: 18px;
    display: grid;
    gap: 18px;
    color: #132958;
    font-size: var(--b2s-fs-md);
    line-height: 1.55;
  }

  .sr-add-empty-state,
  .sr-add-empty-compact {
    border: 1px dashed #ced8ea;
    border-radius: var(--b2s-radius-md);
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
    font-size: var(--b2s-fs-lg);
  }

  .sr-add-empty-state span,
  .sr-add-empty-compact {
    font-size: var(--b2s-fs-sm);
  }

  .sr-add-discovery-btn:disabled,
  .sr-add-refresh-all:disabled {
    cursor: not-allowed;
    opacity: .55;
    box-shadow: none;
  }

  .sr-add-dot {
    width: 7px;
    height: 7px;
    border-radius: var(--b2s-radius-pill);
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
  }

  @media (max-width: 760px) {

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
