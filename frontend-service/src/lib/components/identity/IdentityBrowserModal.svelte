<script lang="ts">
  import LoadingState from '$lib/components/ui/LoadingState.svelte';
  import InlineAlert from '$lib/components/ui/InlineAlert.svelte';
  import StatusBadge from '$lib/components/ui/StatusBadge.svelte';
  import AppModal from '$lib/components/ui/AppModal.svelte';
  import SearchField from '$lib/components/ui/SearchField.svelte';
  import { t } from '$lib/i18n';
  import { formatDateTime, initials, timeAgo } from '$lib/utils/format';
  import { createEventDispatcher, onDestroy } from 'svelte';
  import TreeNode from './TreeNode.svelte';
  import IdentitySelectedPrincipalRow from './IdentitySelectedPrincipalRow.svelte';
  import { invalidateIdentitySourceInternalCache, loadIdentitySourceLastSync } from '../../api/identity-browser';
  import {
    bootstrapIdentityBrowser,
    loadBrowserPreviewForRow,
    loadBrowserRootTree,
    loadBrowserSubtree,
    searchBrowserDirectory
  } from './identity-browser.controller';
  import { createIdentityBrowserStore } from '../../stores/identity-browser.store';
  import type { IdentityBrowserSource, IdentityBrowserSelectionPayload } from '../../types/identity-browser';
  import { principalKey as sharedPrincipalKey, principalLabel, type PrincipalSearchItem } from '../../utils/principal-search';
  import { getIdentityJob } from '../../api/identity';
  import { getIdentitySourceInternal, runIdentitySnapshot } from '../../api/identity-sources';
  import { toAppError } from '$lib/errors';
  import { toast } from '../../stores/toast';

  type DirectoryMode = 'single' | 'multiple';
  type TypeFilter = 'all' | 'user' | 'group' | 'ou';
  type BrowserError = { message: string; detail: string | null };

  /**
   * Directory browser (users and groups of an AD identity source), read from its last snapshot:
   * OU tree, results, preview of the selected principal. Single or multiple selection.
   */
  export let open = false;
  export let onClose: () => void = () => {};
  export let onSelect: ((payload: IdentityBrowserSelectionPayload) => void) | null = null;

  export let identitySources: IdentityBrowserSource[] = [];
  export let initialSourceId: number | null = null;
  export let sourceId: number | null = null;
  export let storageRootId: number | null = null;

  export let title = t('Browse Active Directory');
  export let subtitle = t('Select users or groups to add to this governance role.');
  export let previewTitle = t('Preview');
  export let selectedItemsTitle = t('Selected items');
  export let mode: DirectoryMode = 'multiple';
  export let allowedPrincipalType: TypeFilter = 'all';
  export let includeImportCandidates = true;
  export let searchLimit = 50;

  export let initialSelectedKeys: string[] = [];
  export let initialRoleByKey: Record<string, { guardian?: boolean }> = {};

  export let busy = false;
  export let confirmLabel = t('Use Selected');
  export let confirmBusyLabel = t('Applying…');

  const dispatch = createEventDispatcher<{ close: void; confirm: IdentityBrowserSelectionPayload }>();
  const store = createIdentityBrowserStore();
  const STALE_AFTER_MS = 24 * 3600 * 1000;

  let wasOpen = false;
  let typeFilter: TypeFilter = allowedPrincipalType;
  let expandedDns = new Set<string>();
  let loadingDns = new Set<string>();
  let selectedSourceId: number | null = null;
  let resolvedRootDn: string | null = null;
  let syncing = false;
  let lastSyncAt: string | null = null;
  let error: BrowserError | null = null;
  let searchTimer: ReturnType<typeof setTimeout> | null = null;

  $: selectedSource = ($store.sources ?? []).find((src) => Number(src?.id ?? 0) === Number(selectedSourceId ?? 0)) ?? null;
  $: searchable = selectedSource?.searchable !== false;
  $: snapshotAt = selectedSource?.lastSnapshotAt ?? lastSyncAt;
  $: snapshotStale = Boolean(snapshotAt) && Date.now() - new Date(String(snapshotAt)).getTime() > STALE_AFTER_MS;
  $: showTypeFilter = allowedPrincipalType === 'all';
  $: TYPE_FILTERS = [['all', t('All')], ['user', t('Users')], ['group', t('Groups')]] as Array<[TypeFilter, string]>;
  $: limit = Math.max(1, Math.min(200, Math.trunc(Number(searchLimit || 50) || 50)));
  $: limitReached = $store.rows.length >= limit;

  // ---- Errors: readable message + raw detail for the support
  function toBrowserError(raw: unknown, fallback: string): BrowserError {
    const detail = String((raw as Error)?.message ?? raw ?? '').trim() || null;
    const text = (detail ?? '').toLowerCase();
    const rules: Array<[string[], string]> = [
      [['password', 'secret'], t('The password of the service account of this source is missing.')],
      [['invalid credentials', 'authentication', 'bind failed'], t('The service account could not sign in to the directory.')],
      [['certificate', 'ssl', 'tls', 'ca public key', 'ldap_ca_file'], t('The certificate of the directory server was refused.')],
      [['timeout', 'timed out', 'unreachable', 'connect', 'refused'], t('The directory server did not answer.')],
      [['snapshot is disabled', 'snapshot_disabled'], t('Snapshots are disabled for this source.')]
    ];
    const match = rules.find(([needles]) => needles.some((needle) => text.includes(needle)));
    return { message: match ? match[1] : fallback, detail };
  }

  // ---- Requests in flight (aborted when the source changes or the window closes)
  const activeControllers = new Set<AbortController>();
  const registerController = () => {
    const controller = new AbortController();
    activeControllers.add(controller);
    return controller;
  };
  const releaseController = (controller: AbortController) => activeControllers.delete(controller);
  const abortAllRequests = () => {
    for (const controller of activeControllers) controller.abort();
    activeControllers.clear();
  };

  onDestroy(() => {
    abortAllRequests();
    if (searchTimer) clearTimeout(searchTimer);
  });

  const principalKey = (item: PrincipalSearchItem) =>
    String(sharedPrincipalKey(item as Record<string, unknown>) ?? '').trim().toLowerCase();
  const labelFor = (item: PrincipalSearchItem | Record<string, unknown> | null | undefined): string =>
    principalLabel((item ?? {}) as Record<string, unknown>);
  const typeOf = (item: any): 'user' | 'group' | 'ou' => {
    const value = String(item?.type ?? 'user').toLowerCase();
    return value === 'group' || value === 'ou' ? value : 'user';
  };
  const typeLabel = (item: any): string => ({ user: t('User'), group: t('Group'), ou: 'OU' })[typeOf(item)];
  const secondaryInfo = (row: PrincipalSearchItem): string => {
    const login = String(row?.username ?? row?.upn ?? '').trim();
    const email = String(row?.email ?? '').trim();
    return [login, email].filter(Boolean).join(' · ') || String(row?.ou ?? row?.dn ?? '').trim();
  };
  const isImported = (row: any): boolean => !row?.is_import_candidate;
  const isSelected = (row: PrincipalSearchItem): boolean => $store.selectedKeys.includes(principalKey(row));

  $: previewFields = (() => {
    const p: any = $store.preview;
    if (!p) return [];
    return [
      { label: t('Username'), value: p.username ?? p.sam_account_name, mono: true },
      { label: t('Email'), value: p.email },
      { label: 'UPN', value: p.upn, mono: true },
      { label: t('Distinguished name'), value: p.dn, mono: true },
      { label: t('Members'), value: typeOf(p) === 'group' ? p.member_count ?? p.group_count : null }
    ].filter((field) => field.value !== null && field.value !== undefined && String(field.value).trim() !== '' && String(field.value) !== '-');
  })();

  // ---- Opening and source selection
  function normalizeSelectionFromProps() {
    const keys = Array.from(new Set((initialSelectedKeys ?? []).filter(Boolean)));
    const roleByKey: Record<string, { guardian: boolean }> = {};
    for (const key of keys) roleByKey[key] = { guardian: Boolean(initialRoleByKey?.[key]?.guardian ?? true) };
    store.setSelectedItems(keys, {}, roleByKey);
  }

  async function initializeForOpen() {
    normalizeSelectionFromProps();
    typeFilter = allowedPrincipalType;
    error = null;
    store.setError(null);
    store.setLoading('loadingSources', true);
    try {
      const bootstrap = await bootstrapIdentityBrowser(fetch, { identitySources, initialSourceId, sourceId, storageRootId });
      selectedSourceId = bootstrap.selectedSourceId;
      resolvedRootDn = bootstrap.resolvedRootDn;
      store.setSources(bootstrap.sources, selectedSourceId);
      if (!selectedSourceId) {
        error = { message: t('No active Active Directory identity source.'), detail: null };
        return;
      }
      await handleSourceChange(selectedSourceId, { rootDnOverride: resolvedRootDn, keepSelection: true });
    } catch (e) {
      error = toBrowserError(e, t('The identity sources could not be loaded.'));
    } finally {
      store.setLoading('loadingSources', false);
    }
  }

  async function handleSourceChange(
    nextSourceId: number | null,
    options: { rootDnOverride?: string | null; keepSelection?: boolean } = {}
  ) {
    abortAllRequests();
    expandedDns = new Set();
    loadingDns = new Set();
    error = null;
    if (options.rootDnOverride !== undefined) resolvedRootDn = String(options.rootDnOverride ?? '').trim() || null;
    selectedSourceId = nextSourceId;
    store.resetForSource(nextSourceId);
    // A selection belongs to one directory: never carry it over to another source
    if (!options.keepSelection) store.setSelectedItems([], {}, {});
    const source = ($store.sources ?? []).find((src) => Number(src?.id ?? 0) === Number(nextSourceId ?? 0));
    if (!resolvedRootDn) resolvedRootDn = String(source?.baseDn ?? '').trim() || null;
    if (!nextSourceId || source?.searchable === false) return;
    await loadRootTree(nextSourceId, resolvedRootDn);
    await executeSearch();
    lastSyncAt = await loadIdentitySourceLastSync(fetch, nextSourceId);
  }

  function onSourceSelectChange(event: Event) {
    const nextId = Number((event.currentTarget as HTMLSelectElement | null)?.value ?? 0) || null;
    resolvedRootDn = null;
    void handleSourceChange(nextId, { rootDnOverride: null });
  }

  // ---- Tree
  async function loadRootTree(source: number, rootDn: string | null) {
    const controller = registerController();
    store.setLoading('loadingTree', true);
    try {
      const result = await loadBrowserRootTree(fetch, { sourceId: source, resolvedRootDn: rootDn, signal: controller.signal });
      if (controller.signal.aborted) return;
      store.setTree(result.nodes);
      store.setActiveDn(result.firstDn);
      if (result.firstDn) expandedDns = new Set([...expandedDns, result.firstDn]);
    } catch (e) {
      if (!controller.signal.aborted) error = toBrowserError(e, t('The directory tree could not be loaded.'));
    } finally {
      releaseController(controller);
      if (!controller.signal.aborted) store.setLoading('loadingTree', false);
    }
  }

  function findTreeNode(nodes: any[], dn: string): any {
    for (const node of nodes ?? []) {
      if (node?.dn === dn) return node;
      const fromChild = findTreeNode(node?.children ?? [], dn);
      if (fromChild) return fromChild;
    }
    return null;
  }

  async function toggleTreeNode(event: CustomEvent<{ dn: string; expanded: boolean }>) {
    const { dn, expanded } = event.detail;
    if (!dn || !selectedSourceId) return;
    if (!expanded) {
      const next = new Set(expandedDns);
      next.delete(dn);
      expandedDns = next;
      return;
    }
    expandedDns = new Set([...expandedDns, dn]);
    if (loadingDns.has(dn) || findTreeNode($store.tree, dn)?.loaded) return;
    loadingDns = new Set([...loadingDns, dn]);
    const controller = registerController();
    try {
      const children = await loadBrowserSubtree(fetch, { sourceId: selectedSourceId, dn, resolvedRootDn, signal: controller.signal });
      if (!controller.signal.aborted) store.mergeChildren(dn, children);
    } catch (e) {
      if (!controller.signal.aborted) error = toBrowserError(e, t('This organizational unit could not be opened.'));
    } finally {
      releaseController(controller);
      const next = new Set(loadingDns);
      next.delete(dn);
      loadingDns = next;
    }
  }

  function selectTreeNode(event: CustomEvent<{ dn: string }>) {
    store.setActiveDn(event.detail.dn);
    void executeSearch();
  }

  // ---- Search (typing searches after a short pause; Enter searches at once)
  async function executeSearch() {
    if (!selectedSourceId || !searchable) return;
    store.setRows([], 0);
    const controller = registerController();
    store.setLoading('loadingSearch', true);
    try {
      const response = await searchBrowserDirectory(
        fetch,
        {
          selectedSourceId,
          query: String($store.query ?? '').trim(),
          activeDn: String($store.activeDn ?? '').trim() || null,
          resolvedRootDn,
          principalTypeFilter: typeFilter,
          searchLimit: limit,
          includeImportCandidates
        },
        controller.signal
      );
      if (!controller.signal.aborted) store.setRows(response.rows, response.total);
    } catch (e) {
      if (!controller.signal.aborted) error = toBrowserError(e, t('The search failed.'));
    } finally {
      releaseController(controller);
      if (!controller.signal.aborted) store.setLoading('loadingSearch', false);
    }
  }

  function onQueryChange(value: string) {
    store.setQuery(value);
    if (searchTimer) clearTimeout(searchTimer);
    searchTimer = setTimeout(() => void executeSearch(), 350);
  }

  function setTypeFilter(value: TypeFilter) {
    typeFilter = value;
    void executeSearch();
  }

  // ---- Snapshot of the directory
  const SNAPSHOT_DONE = ['success', 'done', 'succeeded'];

  /** Wait for a snapshot started elsewhere (another admin, another page, the scheduler). */
  async function waitForServerSnapshot(sourceId: number): Promise<void> {
    for (let attempt = 0; attempt < 120; attempt += 1) {
      invalidateIdentitySourceInternalCache(sourceId);
      const internal: any = await getIdentitySourceInternal(fetch, sourceId);
      if (!internal?.snapshot_running) return;
      await new Promise((resolve) => setTimeout(resolve, 3000));
    }
    throw new Error('timeout');
  }

  async function syncDirectory(options: { follow?: boolean } = {}) {
    if (!selectedSourceId || syncing || !selectedSource?.canRunSnapshot) return;
    const sourceId = Number(selectedSourceId);
    syncing = true;
    error = null;
    try {
      let followed = Boolean(options.follow);
      if (!followed) {
        try {
          const run: any = await runIdentitySnapshot(fetch, sourceId, 'auto');
          const jobId = Number(run?.job_id ?? 0);
          if (!(jobId > 0)) throw new Error('Snapshot job not created');
          let status = '';
          for (let attempt = 0; attempt < 60; attempt += 1) {
            const state: any = await getIdentityJob(fetch, jobId);
            status = String(state?.status ?? '').trim().toLowerCase();
            if (SNAPSHOT_DONE.includes(status)) break;
            if (['failed', 'error'].includes(status)) throw new Error(String(state?.error?.message ?? 'Snapshot failed'));
            await new Promise((resolve) => setTimeout(resolve, 1500));
          }
          if (!SNAPSHOT_DONE.includes(status)) throw new Error('timeout');
        } catch (e) {
          if (toAppError(e).code !== 'SNAPSHOT_ALREADY_RUNNING') throw e;
          toast.info(t('A snapshot is already running for this identity source.'));
          followed = true;
        }
      }
      if (followed) await waitForServerSnapshot(sourceId);
      invalidateIdentitySourceInternalCache(sourceId);
      // The source becomes searchable once its first snapshot exists
      store.setSources(
        ($store.sources ?? []).map((src) =>
          Number(src.id) === sourceId
            ? { ...src, searchable: true, snapshotRunning: false, lastSnapshotAt: new Date().toISOString() }
            : src
        ),
        sourceId
      );
      await handleSourceChange(sourceId, { keepSelection: true });
      lastSyncAt = await loadIdentitySourceLastSync(fetch, sourceId, { force: true });
      toast.success(t('Directory synchronized.'));
    } catch (e) {
      error = toBrowserError(e, t('The directory synchronization failed.'));
    } finally {
      syncing = false;
    }
  }

  // A snapshot already running on the selected source: follow it (button greyed meanwhile)
  let followedSourceId: number | null = null;
  $: if (open && selectedSource?.snapshotRunning && !syncing && followedSourceId !== Number(selectedSource.id)) {
    followedSourceId = Number(selectedSource.id);
    void syncDirectory({ follow: true });
  }

  // ---- Selection and preview
  function updateSelection(item: PrincipalSearchItem, checked: boolean) {
    const key = principalKey(item);
    if (!key) return;
    const selectedKeys = mode === 'single' ? [] : [...$store.selectedKeys];
    const selectedCache = mode === 'single' ? {} : { ...$store.selectedCache };
    const roleByKey = { ...$store.roleByKey };
    if (checked) {
      if (!selectedKeys.includes(key)) selectedKeys.push(key);
      selectedCache[key] = { ...item };
    } else {
      selectedKeys.splice(selectedKeys.indexOf(key), 1);
      delete selectedCache[key];
      delete roleByKey[key];
    }
    store.setSelectedItems(selectedKeys, selectedCache, roleByKey);
  }

  async function openPreview(item: PrincipalSearchItem) {
    store.setSelectedKey(principalKey(item));
    if (!String(item?.dn ?? '').trim() || !selectedSourceId) {
      store.setPreview(item as Record<string, unknown>, null);
      return;
    }
    const controller = registerController();
    store.setLoading('loadingPreview', true);
    try {
      const preview = await loadBrowserPreviewForRow(fetch, { selectedSourceId, item, signal: controller.signal });
      if (!controller.signal.aborted) store.setPreview((preview ?? item) as Record<string, unknown>, null);
    } catch {
      if (!controller.signal.aborted) store.setPreview(item as Record<string, unknown>, null);
    } finally {
      releaseController(controller);
      if (!controller.signal.aborted) store.setLoading('loadingPreview', false);
    }
  }

  // Click on a row: single = select it; multiple = toggle it. The preview follows the row.
  function activateRow(item: PrincipalSearchItem) {
    if (busy) return;
    updateSelection(item, mode === 'single' ? true : !isSelected(item));
    void openPreview(item);
  }

  function removeSelectionByKey(key: string) {
    const selectedKeys = $store.selectedKeys.filter((value) => value !== key);
    const selectedCache = { ...$store.selectedCache };
    const roleByKey = { ...$store.roleByKey };
    delete selectedCache[key];
    delete roleByKey[key];
    store.setSelectedItems(selectedKeys, selectedCache, roleByKey);
  }

  function selectionPayload(): IdentityBrowserSelectionPayload {
    const roleByKey: Record<string, { guardian: boolean }> = {};
    for (const key of $store.selectedKeys) roleByKey[key] = { guardian: Boolean($store.roleByKey[key]?.guardian) };
    return {
      sourceId: selectedSourceId,
      query: String($store.query ?? '').trim(),
      selectedKeys: [...$store.selectedKeys],
      selectedItems: $store.selectedKeys
        .map((key) => $store.selectedCache[key])
        .filter((item): item is PrincipalSearchItem => Boolean(item))
        .map((item) => ({ ...item })),
      roleByKey,
      importRole: 'user'
    };
  }

  function closeModal() {
    abortAllRequests();
    open = false;
    dispatch('close');
    onClose();
  }

  function confirmSelection() {
    const payload = selectionPayload();
    dispatch('confirm', payload);
    onSelect?.(payload);
  }

  $: if (open && !wasOpen) {
    wasOpen = true;
    void initializeForOpen();
  }

  $: if (!open && wasOpen) {
    wasOpen = false;
    abortAllRequests();
  }
</script>

<AppModal
  {open}
  onClose={closeModal}
  size="xl"
  modalClass="b2s-modal idb-dialog"
  contentClass="b2s-modal-content idb-content"
  iconClass="bi bi-diagram-3"
  {title}
  {subtitle}
  useFly={false}
>
  <div class="idb">
    <div class="idb-toolbar">
      <select
        class="b2s-select idb-source"
        aria-label={t('Identity source')}
        value={selectedSourceId ?? ''}
        disabled={$store.loadingSources || busy || syncing}
        on:change={onSourceSelectChange}
      >
        {#if $store.sources.length === 0}
          <option value="">{t('No active source')}</option>
        {/if}
        {#each $store.sources as src (src.id)}
          <option value={src.id}>{src.searchable === false ? t('{name} (no snapshot)', { name: src.name }) : src.name}</option>
        {/each}
      </select>

      <SearchField
        wrapperClass="idb-search"
        placeholder={t('Search name, login or email…')}
        ariaLabel={t('Search users or groups')}
        value={$store.query}
        disabled={$store.loadingSources || busy || !searchable}
        onChange={onQueryChange}
        onEnter={() => void executeSearch()}
      />

      {#if showTypeFilter}
        <div class="idb-segments" role="group" aria-label={t('Type')}>
          {#each TYPE_FILTERS as [value, label]}
            <button type="button" class:is-active={typeFilter === value} aria-pressed={typeFilter === value} disabled={!searchable} on:click={() => setTypeFilter(value)}>
              {label}
            </button>
          {/each}
        </div>
      {/if}

      <div class="idb-sync">
        {#if selectedSource && searchable}
          <span class="idb-chip" class:is-stale={snapshotStale} title={snapshotAt ? formatDateTime(snapshotAt) : ''}>
            <i class={`bi ${snapshotStale ? 'bi-exclamation-triangle' : 'bi-clock-history'}`} aria-hidden="true"></i>
            {t('Snapshot {age}', { age: snapshotAt ? timeAgo(snapshotAt) : '—' })}
            {#if selectedSource.usersCount || selectedSource.groupsCount}
              · {t('{users} users · {groups} groups', { users: selectedSource.usersCount ?? 0, groups: selectedSource.groupsCount ?? 0 })}
            {/if}
          </span>
        {/if}
        {#if selectedSource?.canRunSnapshot}
          <button type="button" class="b2s-btn b2s-btn-secondary b2s-btn-sm" disabled={busy || syncing || !selectedSourceId} on:click={() => syncDirectory()}>
            <i class={`bi ${syncing ? 'bi-hourglass-split' : 'bi-arrow-repeat'}`} aria-hidden="true"></i>
            {syncing ? t('Synchronizing…') : t('Synchronize')}
          </button>
        {/if}
      </div>
    </div>

    {#if error}
      <InlineAlert tone="error">
        <strong>{error.message}</strong>
        <a href="/admin/identity-sources">{t('Check the identity source')}</a>
        {#if error.detail && error.detail !== error.message}<small class="idb-error-detail">{error.detail}</small>{/if}
      </InlineAlert>
    {:else if selectedSource && !searchable}
      <InlineAlert tone="warning">
        <strong>{t('This source has no directory snapshot yet.')}</strong>
        {#if selectedSource.canRunSnapshot}
          {t('Synchronize it to search its users and groups.')}
        {:else}
          {t('Enable “Snapshot inventory” on the identity source, then synchronize it.')}
          <a href="/admin/identity-sources">{t('Open identity sources')}</a>
        {/if}
      </InlineAlert>
    {:else if snapshotStale}
      <InlineAlert tone="warning">
        {t('The snapshot is more than a day old: recent accounts may be missing.')}
      </InlineAlert>
    {/if}

    {#if selectedSource && !searchable}
      <div class="idb-placeholder">
        <i class="bi bi-database-x" aria-hidden="true"></i>
        <strong>{t('Nothing to show until the source is synchronized.')}</strong>
        {#if selectedSource.canRunSnapshot}
          <button type="button" class="b2s-btn b2s-btn-primary" disabled={busy || syncing} on:click={() => syncDirectory()}>
            <i class={`bi ${syncing ? 'bi-hourglass-split' : 'bi-arrow-repeat'}`} aria-hidden="true"></i>
            {syncing ? t('Synchronizing…') : t('Synchronize now')}
          </button>
        {/if}
      </div>
    {:else}
    <div class="idb-layout" class:is-single={mode === 'single'}>
      <section class="idb-panel idb-tree" aria-label={t('Directory tree')}>
        <h3 class="idb-panel__title">{t('Directory')}</h3>
        <div class="idb-scroll">
          {#if $store.loadingTree}
            <LoadingState>{t('Loading…')}</LoadingState>
          {:else if $store.tree.length === 0}
            <p class="idb-muted">{searchable ? t('No organizational unit.') : '—'}</p>
          {:else}
            {#each $store.tree as node (node.dn)}
              <TreeNode {node} activeDn={$store.activeDn} {expandedDns} {loadingDns} on:toggle={toggleTreeNode} on:select={selectTreeNode} />
            {/each}
          {/if}
        </div>
      </section>

      <section class="idb-panel idb-results" aria-label={t('Results')}>
        <h3 class="idb-panel__title">
          {t('Results')}
          {#if !$store.loadingSearch && searchable}
            <span>{limitReached ? t('first {count}, refine the search', { count: $store.rows.length }) : $store.rows.length}</span>
          {/if}
        </h3>
        <div class="idb-scroll">
          {#if $store.loadingSearch}
            <LoadingState>{t('Searching the directory…')}</LoadingState>
          {:else if $store.rows.length === 0}
            <p class="idb-empty">
              <i class="bi bi-search" aria-hidden="true"></i>
              {String($store.query ?? '').trim() ? t('No user or group matches this search.') : t('No user or group in this organizational unit.')}
            </p>
          {:else}
            <ul class="idb-rows">
              {#each $store.rows as row (principalKey(row))}
                {@const selected = isSelected(row)}
                <li>
                  <button
                    type="button"
                    class="idb-row"
                    class:is-selected={selected}
                    class:is-previewed={$store.selectedKey === principalKey(row)}
                    aria-pressed={selected}
                    disabled={busy}
                    on:click={() => activateRow(row)}
                  >
                    {#if mode === 'multiple'}
                      <span class="idb-check" aria-hidden="true"><i class={`bi ${selected ? 'bi-check-square-fill' : 'bi-square'}`}></i></span>
                    {/if}
                    <span class={`idb-avatar is-${typeOf(row)}`} aria-hidden="true">
                      {#if typeOf(row) === 'group'}<i class="bi bi-people"></i>{:else}{initials(labelFor(row), '?')}{/if}
                    </span>
                    <span class="idb-row__text">
                      <strong>{labelFor(row)}</strong>
                      <small>{secondaryInfo(row)}</small>
                    </span>
                    <span class="idb-row__badges">
                      <StatusBadge compact showDot={false} variant={typeOf(row) === 'group' ? 'info' : 'muted'} label={typeLabel(row)} />
                      {#if isImported(row)}<StatusBadge compact variant="success" label={t('Imported')} />{/if}
                    </span>
                  </button>
                </li>
              {/each}
            </ul>
          {/if}
        </div>
      </section>

      <section class="idb-panel idb-preview" aria-label={previewTitle}>
        <h3 class="idb-panel__title">{previewTitle}</h3>
        <div class="idb-scroll">
          {#if $store.loadingPreview}
            <LoadingState>{t('Loading…')}</LoadingState>
          {:else if !$store.preview}
            <p class="idb-empty">{t('Select a user or a group to see its details.')}</p>
          {:else}
            {@const p = $store.preview}
            <div class="idb-preview__head">
              <span class={`idb-avatar is-${typeOf(p)}`} aria-hidden="true">
                {#if typeOf(p) === 'group'}<i class="bi bi-people"></i>{:else}{initials(labelFor(p), '?')}{/if}
              </span>
              <div>
                <strong>{labelFor(p)}</strong>
                <small>{typeLabel(p)}{isImported(p) ? ` · ${t('Imported')}` : ''}</small>
              </div>
            </div>
            <dl class="idb-kv">
              {#each previewFields as field}
                <dt>{field.label}</dt>
                <dd class:mono={field.mono}>{field.value}</dd>
              {/each}
            </dl>
          {/if}
        </div>

        {#if mode === 'multiple' && $store.selectedKeys.length > 0}
          <div class="idb-selection">
            <h4>{selectedItemsTitle} <span>{$store.selectedKeys.length}</span></h4>
            <div class="idb-selection__list">
              {#each $store.selectedKeys as key (key)}
                <IdentitySelectedPrincipalRow item={$store.selectedCache[key]} selectionKey={key} onRemove={removeSelectionByKey} />
              {/each}
            </div>
          </div>
        {/if}
      </section>
    </div>
    {/if}
  </div>

  <svelte:fragment slot="footer-start">
    {#if mode === 'single'}
      {$store.selectedKeys.length ? labelFor($store.selectedCache[$store.selectedKeys[0]]) || t('1 selected') : t('Nothing selected')}
    {:else}
      {t('{count} selected', { count: $store.selectedKeys.length })}
    {/if}
  </svelte:fragment>
  <svelte:fragment slot="footer">
    <button type="button" class="b2s-btn b2s-btn-secondary" on:click={closeModal} disabled={busy}>{t('Cancel')}</button>
    <button type="button" class="b2s-btn b2s-btn-primary" on:click={confirmSelection} disabled={busy || $store.selectedKeys.length === 0}>
      {busy ? confirmBusyLabel : mode === 'multiple' ? `${confirmLabel} (${$store.selectedKeys.length})` : confirmLabel}
    </button>
  </svelte:fragment>
</AppModal>

<style>
  .idb {
    display: grid;
    gap: 14px;
    min-height: 0;
  }

  .idb-toolbar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 10px;
  }

  .idb-source {
    flex: 0 1 260px;
    min-width: 200px;
  }

  .idb-toolbar :global(.idb-search) {
    flex: 1 1 260px;
    height: 40px;
    padding: 0 12px;
    border-radius: var(--b2s-radius-sm);
  }

  .idb-toolbar :global(.idb-search input) {
    width: 100%;
    border: none;
    outline: none;
    background: transparent;
    font-size: var(--b2s-fs-sm);
  }

  .idb-segments {
    display: inline-flex;
    gap: 2px;
    padding: 3px;
    border-radius: 9px;
    background: var(--b2s-color-neutral-soft);
  }

  .idb-segments button {
    padding: 5px 12px;
    border: none;
    border-radius: 7px;
    background: transparent;
    color: var(--b2s-color-text-soft);
    font-size: var(--b2s-fs-sm);
    cursor: pointer;
  }

  .idb-segments button.is-active {
    background: var(--b2s-color-surface);
    color: var(--b2s-color-text);
    font-weight: 600;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.12);
  }

  .idb-sync {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    margin-left: auto;
  }

  .idb-chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    border-radius: var(--b2s-radius-pill);
    background: var(--b2s-color-neutral-soft);
    color: var(--b2s-color-text-soft);
    font-size: var(--b2s-fs-xs);
    white-space: nowrap;
  }

  .idb-chip.is-stale {
    background: var(--b2s-color-warning-soft);
    color: var(--b2s-color-warning-strong);
  }

  .idb-error-detail {
    display: block;
    margin-top: 4px;
    font-family: var(--b2s-font-mono);
    font-size: var(--b2s-fs-xs);
    opacity: 0.75;
  }

  .idb-placeholder {
    display: grid;
    justify-items: center;
    gap: 12px;
    padding: 56px 16px;
    border: 1px dashed var(--b2s-color-border-soft);
    border-radius: var(--b2s-radius-md);
    color: var(--b2s-color-text-muted);
    text-align: center;
  }

  .idb-placeholder > i {
    font-size: 28px;
    color: var(--b2s-color-text-faint);
  }

  .idb-layout {
    display: grid;
    grid-template-columns: 240px minmax(0, 1fr) 280px;
    gap: 14px;
    height: min(56vh, 560px);
    min-height: 320px;
  }

  .idb-panel {
    display: flex;
    flex-direction: column;
    min-width: 0;
    min-height: 0;
    border: 1px solid var(--b2s-color-border-soft);
    border-radius: var(--b2s-radius-md);
    background: var(--b2s-color-surface);
  }

  .idb-panel__title {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 8px;
    margin: 0;
    padding: 12px 14px 8px;
    color: var(--b2s-color-text-muted);
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }

  .idb-panel__title span {
    font-weight: 500;
    letter-spacing: 0;
    text-transform: none;
  }

  .idb-scroll {
    flex: 1 1 auto;
    min-height: 0;
    overflow: auto;
    padding: 0 8px 10px;
  }

  .idb-muted,
  .idb-empty {
    margin: 0;
    padding: 18px 8px;
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-sm);
    text-align: center;
  }

  .idb-rows {
    display: grid;
    gap: 2px;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .idb-row {
    width: 100%;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 10px;
    border: none;
    border-radius: 10px;
    background: transparent;
    color: var(--b2s-color-text);
    text-align: left;
    cursor: pointer;
  }

  .idb-row:hover {
    background: #f5f8fc;
  }

  .idb-row.is-selected {
    background: #eef4ff;
  }

  .idb-row.is-previewed {
    box-shadow: inset 3px 0 0 var(--b2s-topbar-bg);
  }

  .idb-check {
    color: var(--b2s-color-text-faint);
    font-size: 16px;
  }

  .idb-row.is-selected .idb-check {
    color: var(--b2s-topbar-bg);
  }

  .idb-avatar {
    width: 32px;
    height: 32px;
    flex: 0 0 auto;
    display: grid;
    place-items: center;
    border-radius: var(--b2s-radius-pill);
    background: #e0e7ff;
    color: #3730a3;
    font-size: 12px;
    font-weight: 700;
  }

  .idb-avatar.is-group {
    background: #e0f2fe;
    color: #0369a1;
    font-size: 15px;
  }

  .idb-row__text {
    flex: 1 1 auto;
    min-width: 0;
    display: grid;
  }

  .idb-row__text strong,
  .idb-row__text small {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .idb-row__text strong {
    font-size: var(--b2s-fs-sm);
    font-weight: 500;
  }

  .idb-row__text small {
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-xs);
  }

  .idb-row__badges {
    display: inline-flex;
    flex: 0 0 auto;
    gap: 6px;
  }

  .idb-preview__head {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 4px 6px 12px;
  }

  .idb-preview__head strong,
  .idb-preview__head small {
    display: block;
  }

  .idb-preview__head small {
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-xs);
  }

  .idb-kv {
    display: grid;
    gap: 2px 0;
    margin: 0;
    padding: 0 6px;
    font-size: var(--b2s-fs-sm);
  }

  .idb-kv dt {
    margin-top: 8px;
    color: var(--b2s-color-text-muted);
    font-size: var(--b2s-fs-xs);
  }

  .idb-kv dd {
    margin: 0;
    overflow-wrap: anywhere;
  }

  .idb-kv dd.mono {
    font-family: var(--b2s-font-mono);
    font-size: var(--b2s-fs-xs);
  }

  .idb-selection {
    max-height: 45%;
    overflow: auto;
    padding: 10px 12px;
    border-top: 1px solid #eef2f7;
  }

  .idb-selection h4 {
    display: flex;
    justify-content: space-between;
    margin: 0 0 8px;
    color: var(--b2s-color-text-muted);
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }

  .idb-selection__list {
    display: grid;
    gap: 6px;
  }

  /* Narrow screens: the preview goes under the results */
  @media (max-width: 1180px) {
    .idb-layout {
      grid-template-columns: 220px minmax(0, 1fr);
      grid-template-rows: minmax(0, 1fr) auto;
      height: auto;
    }

    .idb-tree,
    .idb-results {
      height: 46vh;
    }

    .idb-preview {
      grid-column: 1 / -1;
      max-height: 240px;
    }
  }

  @media (max-width: 760px) {
    .idb-layout {
      grid-template-columns: minmax(0, 1fr);
    }

    .idb-tree {
      height: 180px;
    }

    .idb-sync {
      margin-left: 0;
    }
  }
</style>
